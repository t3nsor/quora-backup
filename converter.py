#!/usr/bin/env python3
import argparse
import errno
from html5lib import (HTMLParser, serializer, treebuilders, treewalkers)
import os
import re
import sys
import time
import urllib.error
import urllib.request
from xml.dom.minidom import Node

def log_if_v(msg):
    if args.verbose:
        print('[DEBUG] %s' % msg, file=sys.stderr)

def get_title_node(document):
    for node in document.getElementsByTagName('title'):
        return node
    return None

def get_text_content(node):
    text = ''
    for text_node in node.childNodes:
        if text_node.nodeType == Node.TEXT_NODE:
            text += text_node.data
    return text

# The HTML can mostly be saved as-is. The main changes we want to make are:
# 1) Remove most <span>s and attributes since they are not needed anymore.
# 2) Rewrite relative paths ("/Brian-Bi") to full URLs
# 3) Download a copy of each embedded image
def cleanup_tree(doc, src, dest):
    for child in src.childNodes:
        if child.nodeType == Node.TEXT_NODE:
            # Text nodes can simply be left as-is
            dest.appendChild(child.cloneNode(False))
            continue
        if child.nodeType != Node.ELEMENT_NODE:
            # ???
            raise ValueError()
        # Otherwise, it's an element node.
        if child.tagName in ['br', 'hr']:
            dest.appendChild(child.cloneNode(False))
        elif child.tagName in ['b', 'i', 'u', 'h2', 'ol', 'ul', 'li', 'blockquote', 'wbr', 'p']:
            # This node doesn't need to be modified but its children might.
            # Also, we won't copy over any of its attributes.
            new_node = doc.createElement(child.tagName)
            cleanup_tree(doc, child, new_node)
            dest.appendChild(new_node)
        elif child.getAttribute('data-embed') != '':
            # This is a video. We want to copy the data-embed value, which is HTML for an iframe node.
            # So, we have to parse it into a separate document and import the node.
            iframe_html = child.getAttribute('data-embed')
            parser = HTMLParser(tree=treebuilders.getTreeBuilder('dom'))
            iframe_doc = parser.parse(iframe_html)
            try:
                iframe = iframe_doc.documentElement.childNodes[1].firstChild
                if iframe.tagName != 'iframe':
                    raise ValueError()
                new_node = doc.importNode(iframe, False)
                # Quora uses a protocol-relative URL (//youtube.com/...) so let's make sure we rewrite this.
                src = new_node.getAttribute('src')
                if src.startswith('//'):
                    new_node.setAttribute('src', 'http:' + src)
                # The video will look really bad if we don't explicitly set the dimensions.
                new_node.setAttribute('width', '525')
                new_node.setAttribute('height', '295')
                dest.appendChild(new_node)
            except Exception:
                print('[WARNING] Failed to parse video embed code', file=sys.stderr)
                # Bail out by just copying the original HTML
                dest.appendChild(child.cloneNode(True))
        elif child.tagName == 'code':
            # Inline code block. Strip the attributes.
            new_node = doc.createElement('code')
            dest.appendChild(new_node)
            cleanup_tree(doc, child, new_node)
        elif 'ContentFooter' in child.getAttribute('class') or 'hidden' in child.getAttribute('class'):
            # These are nodes we just want to skip.
            continue
        elif child.tagName in ['span', 'div']:
            # don't insert a span or div; just insert its contents
            cleanup_tree(doc, child, dest)
        elif child.tagName == 'a':
            # A link. We only want to copy the href, and pass the rest through.
            new_node = doc.createElement('a')
            href = child.getAttribute('href')
            if href.startswith('/'):
                href = 'http://quora.com' + href
            new_node.setAttribute('href', href)
            dest.appendChild(new_node)
            cleanup_tree(doc, child, new_node)
        elif child.tagName == 'img':
            src = child.getAttribute('master_src')
            if src == '':
                src = child.getAttribute('src')
            new_node = doc.createElement('img')
            new_node.setAttribute('src', src)
            new_node.setAttribute('alt', child.getAttribute('alt'))
            if args.no_download:
                dest.appendChild(new_node)
                continue
            # Save a copy of the image locally.
            # If an error occurs, just leave the src pointing to Quora.
            try:
                m = re.search('/([^/?]+)(\?|$)', src)
                if m is None:
                    raise ValueError()
                filename = m.group(1)
                if not filename.endswith('.png'):
                    filename += '.png'
                try:
                    img_fd = os.open(args.output_dir + '/' + filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                except OSError as error:
                    if error.errno == errno.EEXIST:
                        log_if_v('Image %s has already been saved; skipping' % filename)
                        new_node.setAttribute('src', filename)
                        continue
                    else:
                        raise
                log_if_v('Downloading image from %s' % src)
                closed = False
                try:
                    img = urllib.request.urlopen(src).read()
                    time.sleep(args.delay)
                    os.write(img_fd, img)
                    os.close(img_fd)
                    closed = True
                except Exception:
                    os.close(img_fd)
                    closed = True
                    try:
                        os.remove(args.output_dir + '/' + filename)
                    except:
                        print('[WARNING] Failed to remove incomplete file %s' % filename, file=sys.stderr)
                    raise
                finally:
                    if not closed:
                        os.close(img_fd)
                    # Don't leave the file there; we will retry it next time.
                # If everything went according to plan, rewrite the src to the local file.
                new_node.setAttribute('src', filename)
            except urllib.error.URLError as error:
                print('[WARNING] Failed to download image from URL %s (%s)' % (src, error.reason), file=sys.stderr)
            except OSError as error:
                print('[WARNING] Failed to save image from URL %s to file %s (%s)' % (src, filename, error.strerror), file=sys.stderr)
            except ValueError:
                print('[WARNING] Failed to determine image name from URL %s' % src, file=sys.stderr)
            finally:
                dest.appendChild(new_node)
        elif child.tagName == 'pre':
            # Block (not inline) code. Quora's HTML already has the desired <pre><code> structure,
            # so we just need to strip the attributes from the <pre>.
            new_node = doc.createElement('pre')
            dest.appendChild(new_node)
            cleanup_tree(doc, child, new_node)
        else:
            print('[WARNING] Unrecognized node', file=sys.stderr)
            # Bail out by just copying the original HTML
            dest.appendChild(child.cloneNode(True))

parser = argparse.ArgumentParser(description = 'Convert answers downloaded from Quora into a more portable HTML format')
parser.add_argument('input_dir', nargs='?', default='./quora-answers', help='directory containing "raw" answers downloaded from Quora')
parser.add_argument('output_dir', nargs='?', default='./quora-answers-cooked', help='where to store the images and converted answers')
parser.add_argument('-d', '--delay', default=0, type=float, help='Time to sleep between downloads, in seconds')
parser.add_argument('-n', '--no_download', action='store_true', help='Do not save images')
parser.add_argument('-v', '--verbose', action='store_true', help='be verbose')

global args
args = parser.parse_args()

# Get a list of answers to convert...
filenames = list(filter(lambda f: f.endswith('.html'), os.listdir(args.input_dir)))
filenames.sort()
if len(filenames) == 0:
    sys.exit('[FATAL] No .html files found in directory %s', args.input_dir)
print('Found %d answers' % len(filenames), file=sys.stderr)

log_if_v('Creating directory %s' % args.output_dir)
try:
    os.mkdir(args.output_dir, 0o700)
except OSError as error:
    if error.errno == errno.EEXIST:
        log_if_v('Directory already exists')
    else:
        # This is the top level, and we have nothing else to do if we failed
        raise

for filename in filenames:
    sys.stderr.flush()
    print('Filename: ' + filename, file=sys.stderr)
    try:
        with open(args.input_dir + '/' + filename, 'rb') as page:
            page_html = page.read()
    except IOError as error:
        print('[ERROR] Failed to read %s (%s)' % (filename, error.strerror))
        continue

    # Get the HTML element containing just the answer itself.
    # Also get the title.
    parser = HTMLParser(tree=treebuilders.getTreeBuilder('dom'))
    document = parser.parse(page_html, default_encoding='utf-8')
    title_node = get_title_node(document) 
    log_if_v('Title: ' + ('(could not be determined)' if title_node is None else get_text_content(title_node)))

    answer_node = None
    for node in document.getElementsByTagName('div'):
        if 'ExpandedAnswer' in node.getAttribute('class').split():
            answer_node = node
            break
    if answer_node is None:
        print('[WARNING] Failed to locate answer on page (filename: %s)' % filename, file=sys.stderr)
        continue

    # Construct our new page...
    new_page = document.createElement('html')
    head_node = document.createElement('head')
    if not title_node is None:
        head_node.appendChild(title_node)
    meta_node = document.createElement('meta')
    meta_node.setAttribute('charset', 'utf-8')
    head_node.appendChild(meta_node)
    css = ("blockquote { border-left: 2px solid #ddd; color: #666; margin: 0; padding-left: 16px; } "
           "code, pre { background: #f4f4f4; } "
           "pre, h2 { margin: 0; } "
           "ul { margin: 0 0 0 16px; padding: 8px 0; } "
           "ol { margin: 0 0 0 28px; padding: 8px 0; } "
           "li { margin: 0 0 8px; } ")
    style_node = document.createElement('style')
    style_node.setAttribute('type', 'text/css')
    style_node.appendChild(document.createTextNode(css))
    head_node.appendChild(style_node)
    # Quora now uses MathJax, so set up the configuration object:
    script_node = document.createElement('script')
    script_text = document.createTextNode('window.MathJax = {"showMathMenu":false,"messageStyle":"none","errorSettings":{"style":{"color":"#000000","font-style":"normal"}},"HTML-CSS":{"linebreaks":{"automatic":true,"width":"container"},"EqnChunk":150,"EqnChunkDelay":20},"tex2jax":{"inlineMath":[["[math]","[/math]"]],"displayMath":[],"ignoreClass":"edit_latex|qtext_editor_content|ignore_latex","processClass":"render_latex","processEnvironments":false,"preview":"none"},"TeX":{"noUndefined":{"attributes":{"mathcolor":"red"}},"noErrors":{"multiLine":true,"style":{"max-width":"100%","overflow":"hidden"}},"Macros":{"C":"{\\mathbb{C}}","N":"{\\mathbb{N}}","O":"{\\emptyset}","Q":"{\\mathbb{Q}}","R":"{\\mathbb{R}}","Z":"{\\mathbb{Z}}"}},"fast-preview":{"disabled":true},"Safe":{"allow":{"URLs":"none","classes":"none","cssIDs":"none","styles":"none","fontsize":"none","require":"none"}}};')
    script_node.appendChild(script_text)
    head_node.appendChild(script_node)
    # and then load MathJax:
    script_node = document.createElement('script')
    script_node.setAttribute('type', 'text/javascript')
    script_node.setAttribute('src', 'https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/MathJax.js?config=TeX-AMS-MML_HTMLorMML,Safe')
    head_node.appendChild(script_node)
    new_page.appendChild(head_node)
    body_node = document.createElement('body')
    # This step processes Quora's HTML into a more lightweight and portable form.
    cleanup_tree(document, answer_node, body_node)
    new_page.appendChild(body_node)
    # Okay! Finally, save the HTML.
    walker = treewalkers.getTreeWalker('dom')(new_page)
    try:
        with open(args.output_dir + '/' + filename, 'wb', 0o600) as saved_page:
            saved_page.write(b'<!DOCTYPE html>')
            saved_page.write(serializer.serialize(new_page, 'dom', 'utf-8', omit_optional_tags=False))
    except IOError as error:
        print('[ERROR] Failed to save to file %s (%s)' % (filename, error.strerror), file=sys.stderr)

print('Done', file=sys.stderr)

