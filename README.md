# plenka

A small site for sharing photos and videos with friends. You drop a file, you get a link.
Without accounts and sign-up.

Live at [plenka-pics.ru](https://plenka-pics.ru).


## Why

My friends and I kept sending each other photos through messengers that compress everything and
make it annoying to find stuff later. I wanted something simpler: upload, copy the link, done.
Posts are private by default (only people with the link can open them), and you can flip a switch
to put one in the public feed.

## How it works

There are no user accounts. When you upload something, your browser session remembers that the post
is yours, so you can rename it, hide it from the feed or delete it. You also get a secret
"manage link", which works like Imgur's deletehash: open it on another device and the post becomes
editable there too.

Photos go through Pillow and get re-encoded, which also strips EXIF data (phones love to put GPS
coordinates in there). Videos are transcoded with ffmpeg to H.264 MP4 in a background thread,
so they play everywhere, and the metadata is dropped the same way.

Each post shows a view count and when it was last opened. A daily cleanup job deletes posts that
nobody has opened for 3 months, because the server disk is not infinite.

If something bad gets uploaded, anyone can report it. Five reports and the post is hidden until
I look at it in the admin view on the site.

## Security stuff I spent time on

Since anyone can upload without an account, I tried to be careful with a few things:

- Uploads are checked by their actual content, not the file extension. ffmpeg only accepts real
  MP4/MOV/WebM containers and can't open anything except the uploaded file itself, so you can't
  sneak in a playlist that makes the server fetch URLs or read local files.
- Files are never served from a public folder. nginx only sends a file after Django checks that the
  post still exists and isn't hidden (`X-Accel-Redirect`).
- The admin login is rate limited by IP and by username, and Django's built-in admin login redirects
  to the same page, so the limit can't be skipped. The client IP comes from nginx, not from headers
  the client can fake.
- Link-only posts get `noindex` and `no-referrer` so the links don't leak through search engines
  or referrers.

## Stack

Python, Django, PostgreSQL, Pillow, ffmpeg, nginx + gunicorn. The frontend is plain HTML, CSS and
JavaScript, no frameworks. It supports light and dark themes and works on screens down to 320px.

## Layout

```
photos/
  views.py       pages, uploads, owner actions, moderation, admin login
  models.py      the Post model
  imaging.py     image checks and re-encoding
  video.py       ffprobe/ffmpeg wrapper
  tasks.py       background video processing
  management/commands/cleanup_posts.py
photohost/settings.py   limits and switches
deploy/nginx.conf
```

Made by [Juspear](https://github.com/Juspear)
