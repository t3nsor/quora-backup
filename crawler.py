#!/usr/bin/env python3
import argparse
import errno
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

def log_if_v(msg):
    if args.verbose:
        print('[DEBUG] %s' % msg, file=sys.stderr)

# Given origin (timestamp offset by time zone) and string from Quora, e.g.
# "Added 31 Jan", returns a string such as '2015-01-31'.
# Quora's short date strings don't provide enough information to determine the
# exact time, unless it was within the last day, so we won't bother to be any
# more precise.
def parse_quora_date(origin, quora_str):
    days_of_week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    months_of_year = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    _, _, date_str = quora_str.partition('Added ')
    date_str = date_str.strip()
    if date_str == '':
        raise ValueError('"%s" does not appear to indicate when answer was added' % quora_str)
    m0 = re.match('just now$', date_str)
    m1 = re.match('(\d+)m ago$', date_str)
    m2 = re.match('(\d+)h ago$', date_str)
    m3 = re.match('(' + '|'.join(days_of_week) + ')$', date_str)
    m4 = re.match('(\d+) (' + '|'.join(months_of_year) + ')$', date_str)
    m5 = re.match('(\d+) (' + '|'.join(months_of_year) + ') (\d+)$', date_str)
    m6 = re.match('(\d+)[ap]m$', date_str)
    if not m0 is None or not m6 is None:
        # Using origin for time in am / pm since the time of the day will be discarded anyway
        tm = time.gmtime(origin)
    elif not m1 is None:
        tm = time.gmtime(origin - 60*int(m1.group(1)))
    elif not m2 is None:
        tm = time.gmtime(origin - 3600*int(m2.group(1)))
    elif not m3 is None:
        # Walk backward until we reach the given day of the week
        day_of_week = days_of_week.index(m3.group(1))
        offset = 1
        while offset <= 7:
            tm = time.gmtime(origin - 86400*offset)
            if tm.tm_wday == day_of_week:
                break
            offset += 1
        else:
            raise ValueError('date "%s" is invalid' % date_str)
    elif not m4 is None:
        # Walk backward until we reach the given month and year
        month_of_year = months_of_year.index(m4.group(2)) + 1
        day_of_month = int(m4.group(1))
        offset = 1
        while offset <= 366:
            tm = time.gmtime(origin - 86400*offset)
            if tm.tm_mon == month_of_year and tm.tm_mday == day_of_month:
                break
            offset += 1
        else:
            raise ValueError('date "%s" is invalid' % date_str)
    elif not m5 is None:
        # may raise ValueError
        tm = time.strptime(date_str, '%d %b %Y')
    else:
        raise ValueError('date "%s" could not be interpreted' % date_str)
    return '%d-%02d-%02d' % (tm.tm_year, tm.tm_mon, tm.tm_mday)

parser = argparse.ArgumentParser(description = 'Download a set of answers from Quora')
parser.add_argument('input_file', help='file containing JSON-encoded list of timestamped URLs to download')
parser.add_argument('output_dir', nargs='?', default='./quora-answers', help='where to store the downloaded answers and images')
parser.add_argument('-d', '--delay', default=0, type=float, help='Time to sleep between answers, in seconds')
parser.add_argument('-t', '--origin_timestamp', default=None, type=int, help='JS time when the list of URLs was fetched')
parser.add_argument('-z', '--origin_timezone', default=None, type=int, help='browser timezone')
parser.add_argument('-v', '--verbose', action='store_true', help='enable debug messages')
parser.add_argument('-o', '--overwrite', action='store_true', help='Overwrite existing answers')

global args
args = parser.parse_args()

# Determine the origin for relative date computation
if args.origin_timestamp is None:
    log_if_v('Using current time')
    args.origin_timestamp = time.time()
else:
    args.origin_timestamp //= 1000
if args.origin_timezone is None:
    log_if_v('Using system time zone')
    args.origin_timezone = time.timezone
else:
    args.origin_timezone *= 60
origin = args.origin_timestamp - args.origin_timezone

# Load the list of answer URLs from the input file.
log_if_v('Loading input file %s' % args.input_file)
with open(args.input_file, 'r') as input_file:
    answers = json.load(input_file)
print('Found %d answers' % len(answers), file=sys.stderr)

# Check the validity of the input
if type(answers) != list:
    sys.exit('[FATAL] Incorrect input format')
for e in answers:
    if type(e) != list or len(e) != 2 or type(e[0]) != str or type(e[1]) != str:
        sys.exit('[FATAL] Incorrect input format')

log_if_v('Creating directory %s' % args.output_dir)
try:
    os.mkdir(args.output_dir, 0o700)
except OSError as error:
    if error.errno == errno.EEXIST:
        log_if_v('Directory already exists')
    else:
        # This is the top level, and we have nothing else to do if we failed
        raise
os.chdir(args.output_dir)
download_file_count = 0
for e in answers:
    sys.stderr.flush()
    url = e[0]
    print('URL: %s' % url, file=sys.stderr)

    # Determine the date when this answer was written
    try:
        added_time = parse_quora_date(origin, e[1])
    except ValueError as error:
        print('[WARNING] Failed to parse date: %s' % str(error), file=sys.stderr)
        added_time = 'xxxx-xx-xx'
    print('Date: %s' % added_time, file=sys.stderr)

    # Get the part of the URL indicating the question title; we will save under this name
    m1 = re.search('quora\.com/([^/]+)/answer', url)
    # if there's a context topic
    m2 = re.search('quora\.com/[^/]+/([^/]+)/answer', url)
    filename = added_time + ' '
    if not m1 is None:
        filename += m1.group(1)
    elif not m2 is None:
        filename += m2.group(1)
    else:
        print('[ERROR] Could not find question part of URL %s; skipping' % url, file=sys.stderr)
        continue
    # Trim the filename if it's too long. 255 bytes is the limit on many filesystems.
    total_length = len(filename + '.html')
    if len(filename + '.html') > 255:
        filename = filename[:(255 - len(filename + '.html'))]
        log_if_v('Filename was truncated to 255 characters.')
    filename += '.html'
    log_if_v('Filename: %s' % filename)

    # If overwrite is enabled or the answer doesn't exist
    if args.overwrite or not os.path.isfile(filename):
        # Fetch the URL to find the answer
        log_if_v('Downloading answer from URL %s' % url)
        try:
            page_html = urllib.request.urlopen(url).read()
            with open(filename, 'wb') as f:
                f.write(page_html)
        except urllib.error.URLError as error:
            print('[ERROR] Failed to download answer from URL %s (%s)' % (url, error.reason), file=sys.stderr)
            continue
        except IOError as error:
            print('[ERROR] Failed to save answer to file %s (%s)' % (filename, error.strerror), file=sys.stderr)

        download_file_count += 1
        time.sleep(args.delay)
    else:
        log_if_v('Answer File : %s Already Exists. Skipping' % filename)

print('Done. Downloaded %d files' % download_file_count, file=sys.stderr)
