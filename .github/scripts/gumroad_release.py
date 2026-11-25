"""Update the ATK Gumroad product after a GitHub release is published.

Run by .github/workflows/gumroad-release.yml. Standard library only.

What it does, in order:
1. Finds the Gumroad product (GUMROAD_PRODUCT: an id, or the product's
   permalink such as "animation-tool-kit").
2. Rewrites the product description: every "Version X.Y.Z" / "vX.Y.Z" becomes
   the new version, and the "What's new" block is replaced with the release
   notes (see replace_changelog for how the block is found).
3. Replaces the downloadable ZIP: uploads the release's
   AnimationToolKit_v*.zip with Gumroad's presigned upload flow
   (POST /v2/files/presign, PUT each part, POST /v2/files/complete) and swaps
   it in for the previous AnimationToolKit_v*.zip, keeping every other file.
   Content pages that embed the old ZIP are pointed at the new one in the
   same request.

Any step that cannot be done through the API is written to MANUAL_STEPS_FILE
so the workflow can show it and open an issue. DRY_RUN=true makes no changes.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://api.gumroad.com/v2'
PRODUCT_URL = 'https://shepstone.gumroad.com/l/animation-tool-kit'
ZIP_NAME = re.compile(r'^AnimationToolKit_v\d+_\d+_\d+', re.I)
VERSION_IN_TEXT = re.compile(r'(?i)\b(version\s*|v)(\d+\.\d+\.\d+)\b')
CHANGELOG_START = '<!-- atk-changelog:start -->'
CHANGELOG_END = '<!-- atk-changelog:end -->'
WHATS_NEW_H2 = re.compile(r"<h2[^>]*>\s*What(?:&#39;|'|’|&rsquo;)s new[^<]*</h2>", re.I)


# ---------------------------------------------------------------- text helpers

def parse_version(text):
    """Return 'X.Y.Z' from a tag or name such as ATK_1.1.29 or ATK_v1-1-3."""
    match = re.search(r'(\d+)[.\-_](\d+)[.\-_](\d+)', text or '')
    if not match:
        raise ValueError('No X.Y.Z version in %r' % text)
    return '.'.join(match.groups())


def _vkey(version):
    return tuple(int(part) for part in version.split('.'))


def _inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', text)
    return text


def markdown_to_html(markdown):
    """Small Markdown converter for release notes: headings, paragraphs,
    bullet and numbered lists, bold, italics, code and links. The top-level
    '# Title' is dropped (the block has its own heading) and '##' becomes h3
    so the notes nest under the block's h2."""
    out, para, items, list_tag = [], [], [], None

    def flush():
        nonlocal para, items, list_tag
        if para:
            out.append('<p>%s</p>' % _inline(' '.join(para)))
            para = []
        if items:
            out.append('<%s>%s</%s>' % (list_tag, ''.join('<li>%s</li>' % _inline(i) for i in items), list_tag))
            items, list_tag = [], None

    for raw in markdown.replace('\r\n', '\n').split('\n'):
        line = raw.rstrip()
        heading = re.match(r'^(#{1,6})\s+(.*)$', line)
        bullet = re.match(r'^\s*[-*+]\s+(.*)$', line)
        number = re.match(r'^\s*\d+[.)]\s+(.*)$', line)
        if not line.strip():
            flush()
        elif heading:
            flush()
            level = len(heading.group(1))
            if level > 1:
                tag = 'h%d' % min(level + 1, 6)
                out.append('<%s>%s</%s>' % (tag, _inline(heading.group(2)), tag))
        elif bullet or number:
            tag = 'ul' if bullet else 'ol'
            if para or (items and list_tag != tag):
                flush()
            list_tag = tag
            items.append((bullet or number).group(1))
        elif items and raw[:1].isspace():
            items[-1] += ' ' + line.strip()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return '\n'.join(out)


def changelog_block(version, notes_markdown):
    return '%s\n<h2>What\'s new in %s</h2>\n%s\n%s' % (
        CHANGELOG_START, version, markdown_to_html(notes_markdown), CHANGELOG_END)


def replace_changelog(description, block):
    """Put block in place of the current changelog. Looks, in order, for the
    marker comments, then for an h2 starting "What's new" (up to the next h2),
    and otherwise puts the block at the top. Returns (html, how)."""
    start, end = description.find(CHANGELOG_START), description.find(CHANGELOG_END)
    if start != -1 and end > start:
        return description[:start] + block + description[end + len(CHANGELOG_END):], 'markers'
    heading = WHATS_NEW_H2.search(description)
    if heading:
        following = re.compile(r'<h2[\s>]', re.I).search(description, heading.end())
        stop = following.start() if following else len(description)
        return description[:heading.start()] + block + '\n' + description[stop:], 'heading'
    return block + '\n' + description, 'top'


def bump_versions(text, version):
    """Replace 'Version X.Y.Z' / 'vX.Y.Z' with version where X.Y.Z is older."""
    def sub(match):
        if _vkey(match.group(2)) < _vkey(version):
            return match.group(1) + version
        return match.group(0)
    return VERSION_IN_TEXT.sub(sub, text)


def update_description(description, version, notes_markdown):
    """Return (new_html, how_changelog_was_placed)."""
    description = description or ''
    start, end = description.find(CHANGELOG_START), description.find(CHANGELOG_END)
    if start != -1 and end > start:
        # Leave the old changelog alone while bumping; it is replaced next.
        head = bump_versions(description[:start], version)
        tail = bump_versions(description[end:], version)
        description = head + description[start:end] + tail
    else:
        description = bump_versions(description, version)
    return replace_changelog(description, changelog_block(version, notes_markdown))


def swap_file_embeds(node, old_ids, new_id):
    """Return a copy of a rich-content tree with fileEmbed ids in old_ids
    replaced by new_id, and how many were replaced."""
    count = 0
    if isinstance(node, list):
        result = []
        for child in node:
            copy, n = swap_file_embeds(child, old_ids, new_id)
            result.append(copy)
            count += n
        return result, count
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            copy, n = swap_file_embeds(value, old_ids, new_id)
            result[key] = copy
            count += n
        if result.get('type') == 'fileEmbed' and (result.get('attrs') or {}).get('id') in old_ids:
            result['attrs'] = dict(result['attrs'], id=new_id)
            count += 1
        return result, count
    return node, 0


def plan_files(current_files, new_file_url, new_display_name, client_id):
    """Return (files_param, removed_ids). Keeps every file that is not an
    AnimationToolKit_vX_Y_Z ZIP and puts the new ZIP where the old one was."""
    files, removed, position = [], [], None
    for index, f in enumerate(current_files):
        if ZIP_NAME.match(f.get('name') or ''):
            removed.append(f['id'])
            if position is None:
                position = index
        else:
            files.append({'id': f['id']})
    new_entry = {'id': client_id, 'url': new_file_url, 'display_name': new_display_name}
    files.insert(len(files) if position is None else position, new_entry)
    return files, removed


# ---------------------------------------------------------------- Gumroad API

class GumroadError(RuntimeError):
    pass


class Gumroad:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None, query=None):
        url = API + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'atk-release-workflow',
        })
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode() or '{}')
        except urllib.error.HTTPError as error:
            text = error.read().decode(errors='replace')[:500]
            raise GumroadError('%s %s -> HTTP %s: %s' % (method, path, error.code, text))
        if payload.get('success') is False:
            raise GumroadError('%s %s -> %s' % (method, path, payload.get('message') or payload))
        return payload

    def find_product(self, product):
        try:
            return self.call('GET', '/products/' + urllib.parse.quote(product))['product']
        except GumroadError:
            pass
        # A custom permalink (/l/animation-tool-kit) is not accepted as an id,
        # so look it up in the product list.
        query = {}
        while True:
            page = self.call('GET', '/products', query=query)
            for item in page.get('products', []):
                if product in (item.get('custom_permalink'), item.get('id')) or \
                        (item.get('short_url') or '').rstrip('/').endswith('/' + product):
                    return self.call('GET', '/products/' + item['id'])['product']
            if not page.get('next_page_key'):
                raise GumroadError('No Gumroad product matches %r' % product)
            query = {'page_key': page['next_page_key']}

    def upload(self, path):
        size = path.stat().st_size
        presign = self.call('POST', '/files/presign', {'filename': path.name, 'file_size': size})
        parts, part_size = [], 100 * 1024 * 1024  # Gumroad's PART_SIZE
        try:
            with path.open('rb') as handle:
                for part in presign['parts']:
                    chunk = handle.read(part_size)
                    request = urllib.request.Request(part['presigned_url'], data=chunk, method='PUT')
                    with urllib.request.urlopen(request, timeout=600) as response:
                        parts.append({'part_number': part['part_number'], 'etag': response.headers['ETag']})
            done = self.call('POST', '/files/complete', {
                'upload_id': presign['upload_id'], 'key': presign['key'], 'parts': parts})
        except Exception:
            try:
                self.call('POST', '/files/abort', {'upload_id': presign['upload_id'], 'key': presign['key']})
            except Exception:
                pass
            raise
        return done['file_url']


# ---------------------------------------------------------------- main

def manual_steps(version, zip_path, reasons, description_done, file_done):
    lines = ['## Gumroad needs a manual update for ATK %s' % version, '']
    lines += ['The release workflow could not finish everything through the Gumroad API:', '']
    lines += ['- %s' % reason for reason in reasons] + ['']
    lines += ['Open the product editor from %s (Products → Animation Tool Kit → Edit), then:' % PRODUCT_URL, '']
    step = 1
    if not description_done:
        lines.append('%d. **Product** tab: change the version in the description to **%s** and replace the '
                     '"What\'s new" section with the %s release notes.' % (step, version, version))
        step += 1
    if not file_done:
        name = zip_path.name if zip_path else 'AnimationToolKit_v%s.zip' % version.replace('.', '_')
        lines.append('%d. **Content** tab: upload `%s` from the GitHub release, then delete the previous '
                     'AnimationToolKit ZIP. If a content page embeds the old ZIP, put the new one in its place.'
                     % (step, name))
        step += 1
    lines.append('%d. Click **Save changes**, then open %s to check the page.' % (step, PRODUCT_URL))
    return '\n'.join(lines) + '\n'


def main():
    env = os.environ
    token = env.get('GUMROAD_ACCESS_TOKEN', '').strip()
    tag = env['RELEASE_TAG']
    try:
        version = parse_version(tag)
    except ValueError:
        version = parse_version(env.get('RELEASE_NAME', ''))
    notes = env.get('RELEASE_BODY', '')
    notes_file = Path('Animation_Tool_Kit_v%s_Release_Notes.md' % version)
    if not notes.strip() and notes_file.exists():
        notes = notes_file.read_text(encoding='utf-8')
    dry_run = env.get('DRY_RUN', 'false').lower() == 'true'
    update_file = env.get('UPDATE_FILE', 'true').lower() != 'false'
    product_ref = env.get('GUMROAD_PRODUCT') or 'animation-tool-kit'
    zips = sorted(Path(env.get('ASSETS_DIR', 'release-assets')).glob('AnimationToolKit_v*.zip'))
    zip_path = zips[0] if zips else None
    summary = Path(env['GITHUB_STEP_SUMMARY']) if env.get('GITHUB_STEP_SUMMARY') else None
    manual_file = Path(env.get('MANUAL_STEPS_FILE', 'gumroad-manual-steps.md'))

    log = ['# Gumroad update for ATK %s%s' % (version, ' (dry run)' if dry_run else ''), '']
    reasons, description_done, file_done = [], False, not update_file

    if not token:
        reasons.append('The `GUMROAD_ACCESS_TOKEN` repository secret is not set.')
    else:
        api = Gumroad(token)
        try:
            product = api.find_product(product_ref)
        except GumroadError as error:
            product = None
            reasons.append('Could not read the product: %s' % error)
        if product:
            log.append('Product: **%s** (`%s`)' % (product.get('name'), product['id']))
            # Description and name
            try:
                new_description, how = update_description(product.get('description'), version, notes)
                body = {'description': new_description}
                new_name = bump_versions(product.get('name') or '', version)
                if new_name and new_name != product.get('name'):
                    body['name'] = new_name
                log.append('- Description: version set to %s, changelog placed by %s.' % (version, how))
                if how == 'top':
                    log.append('  No changelog block was found, so a new one was added at the top.')
                if dry_run:
                    log += ['', '<details><summary>New description HTML</summary>', '', '```html',
                            new_description, '```', '</details>', '']
                if not dry_run:
                    api.call('PUT', '/products/' + product['id'], body)
                description_done = True
            except GumroadError as error:
                reasons.append('Updating the description failed: %s' % error)
            # Downloadable file
            if update_file:
                try:
                    if not zip_path:
                        raise GumroadError('the release has no AnimationToolKit_v*.zip asset')
                    client_id = 'cli-upload-atk-%s' % version.replace('.', '-')
                    if dry_run:
                        file_url = '(uploaded in a real run)'
                    else:
                        file_url = api.upload(zip_path)
                    files, removed = plan_files(product.get('files') or [], file_url, zip_path.stem, client_id)
                    body = {'files': files}
                    pages, embeds = [], 0
                    for page in product.get('rich_content') or []:
                        swapped, n = swap_file_embeds(page.get('description'), set(removed), client_id)
                        embeds += n
                        pages.append({'id': page['id'], 'title': page.get('title'), 'description': swapped})
                    if embeds:
                        body['rich_content'] = pages
                    log.append('- File: `%s` replaces %s; %d content-page embed(s) repointed.'
                               % (zip_path.name, ', '.join('`%s`' % i for i in removed) or 'nothing', embeds))
                    if not dry_run:
                        api.call('PUT', '/products/' + product['id'], body)
                    file_done = True
                except (GumroadError, urllib.error.URLError, KeyError) as error:
                    reasons.append('Replacing the downloadable file failed: %s' % error)

    if reasons:
        steps = manual_steps(version, zip_path, reasons, description_done, file_done)
        manual_file.write_text(steps, encoding='utf-8')
        log += ['', steps]
    else:
        log += ['', 'Done. Check %s.' % PRODUCT_URL]
    text = '\n'.join(log) + '\n'
    print(text)
    if summary:
        with summary.open('a', encoding='utf-8') as handle:
            handle.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
