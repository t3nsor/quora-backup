## Installation

You need Python 3, version 3.2 or higher, with the `html5lib` library installed. Pick up a copy [here](https://github.com/html5lib/html5lib-python).

This software is only known to work on Linux. It can probably be made to work in Windows too, but I haven't tried it. Patches welcome.

No installation is required, but make sure that `converter.py` and `crawler.py` are executable. (Or you can just run them by invoking `python3` explicitly.)

## Basic usage: downloading all your answers

To view all your answers, go to the answers section of [Your Content](https://www.quora.com/content?content_types=answers) and scroll all the way down until there are no more answers to load.

Type the following into your browser's URL bar:

    javascript:window.open().document.write(JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.UserContentList .pagedlist_item'), function (e) { return [e.getElementsByTagName('a')[0].href, e.getElementsByClassName('metadata')[0].innerHTML] })))

**Note:** You can copy and paste the code above, but your browser might automatically remove the `javascript:` prefix from the URL when you do so. If that happens, you'll have to type in the `javascript:` part yourself. Alternatively, you can just use the browser console to execute the javascript code.

(You need popups enabled in order for this to work. If your popup blocker blocks the window, disable it and try again.)

This creates a popup window or new tab containing a list of your answers, in a format that looks something like this:

`[["https://www.quora.com/Do-classical-mechanics-work-beyond-the-speed-of-light/answer/Brian-Bi","Added Fri"],["https://www.quora.com/Are-competitive-programmers-happy-when-working-as-software-engineers/answer/Brian-Bi","Added Thu"],["https://www.quora.com/How-did-Brian-Bi-not-know-it-was-Chinese-New-Year-today/answer/Brian-Bi","Added Thu"],["https://www.quora.com/How-many-hours-of-studies-did-Brian-Bi-put-in-per-day-in-order-to-prepare-for-the-IChO/answer/Brian-Bi","Added Thu"]`...

Copy and paste the entire contents of the window or tab into a text editor and save it as a file, `answers.json`.

Go back to your browser, type in the following URL, and press Enter:

`javascript:window.open().document.write(new Date().valueOf() + '<br>' + new Date().getTimezoneOffset())`

(The same caveats as before apply.)

Again a new window or tab should pop up, showing the date in a numeric format, with two lines. The first line shows the current timestamp in numeric format. The second shows the offset of your time zone from UTC in minutes. Take note of both of these numbers.

Suppose you installed the scripts in `/home/brian/quora-backup`. You can run the crawler as follows:

`/home/brian/quora-backup/crawler.py answers.json /home/brian/quora-answers --origin_timestamp=${TIMESTAMP} --origin_timezone=${OFFSET}`

replacing `${TIMESTAMP}` with the timestamp value previously obtained from the browser, and `${OFFSET}` with the time zone offset value.

This creates a new directory, `/home/brian/quora-answers`, and populates it with the answers specified, after downloading them from Quora. It also generates a timestamp in YYYY-MM-DD format for each answer.

## Converting answers to a standalone format

The converter can be run as follows:

`/home/brian/quora-backup/converter.py /home/brian/quora-answers /home/brian/quora-answers-cooked`

This creates the directory `/home/brian/quora-answers-cooked` and copies each answer downloaded into `/home/brian/quora-answers` into the new directory after processing it to remove everything other than the answer content itself. If this step succeeds, then the answer will still be readable even if Quora disappears from the face of the Web.

## What the crawler does

The crawler is pretty simple: its job is to download the URLs you provide. But it also has a slightly nontrivial task, which is to determine the date on which each answer was written (give or take a day). This is done by reading the timestamps provided on the Your Content page itself. But the more recent timestamps given are relative, not absolute (for example, "Fri" if you wrote answer last Friday). That's why the crawler needs to be told at what time you accessed that page and in what time zone, so it can resolve those strings into absolute dates.

## What the converter does

The converter has three main functions:

1. It removes everything on the page other than the answer content. No bar at the top, no sidebar with related answers, no box indicating why the answer was collapsed (if it was); your name is not shown, nor are upvotes, the timestamp, view count, comments, or the upvote and downvote buttons. All that's left is answer content. This also reduces the size of the HTML considerably.
2. It downloads a copy of each image embedded in your answer. These images are
all hosted on Quora's servers; after running the converter, you'll have a copy on local disk, so you'll still be able to view the images even if Quora disappears. (This functionality can be disabled using the `-n` flag.)
3. It removes extraneous HTML elements and attributes, simplifying the HTML as much as possible.

## FAQ

**Why did you write your own Quora backup tool when there are already a zillion of them?**

Because I believe this tool is unique in that it allows you to reliably and easily download ALL your answers, even if you have thousands of them, AND to ensure that they still display properly even if Quora completely disappears.

**What if I only want to download some of my answers?**

To download only some of your answers, just remove all the entries from `answers.json` you don't want. If you also just want to download some recent answers, you don't have to scroll all the way down on the "Your Content" page. Yes, I realize this is really user-unfriendly. It would be nice to have a GUI. Patches welcome.

**Won't Quora flag me for using a script to automatically download answers?**

It depends on how many answers you're downloading. If it's less than a thousand, you'll probably be fine, but I take no responsibility if something bad happens to you. If you have a LOT of answers, you might want to take advantage of the built-in rate limiting options. Both the crawler and converter support a `--delay` flag; for example, `--delay=1` tells the script to pause for a second after every download. Don't ask me what value to use here; I don't know. Use this software at your own risk.

**Why is this licensed under the GPL? I noticed you usually prefer more permissive licenses.**

Because I want to make sure that all changes get merged back into my repository. There is a very good reason for this: there is only one Quora, and they'll probably change the way they generate HTML, which means this software will periodically stop working properly. I want to maintain a single version that's fully up to date with all the patches other people submit, rather than having multiple versions running around with patches for different kinds of elements.

## Errors and bugs
A message starting with [FATAL] signals that the script cannot function at all. [ERROR] means that processing of a single answer was aborted due to an unrecoverable error; [WARNING] means an error condition arose which prevented some feature from working properly but did not abort the processing of an answer. If you run with the `-v` flag, you'll also see [DEBUG] messages.

The converter will emit a [WARNING] message if it doesn't understand the HTML found in the answer. I have tested the converter against my entire set of answers, so I believe that as of the time of this release, this should never happen. But the format of Quora's HTML is likely to change in the future, which means the converter will stop working properly. If this happens, you're likely to see [WARNING] messages. Those should be reported.

If you want to report such a bug in the converter, try re-running with the "-v" flag, and include with your report everything between the closest "Filename:" lines before and after the [WARNING] message. (This doesn't mean other kinds of bugs shouldn't be reported; I am just giving instructions on how to report the most common kind of bug I expect.)
