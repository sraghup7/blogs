# blogs

My blog. Published with GitHub Pages at <https://sraghup7.github.io/blogs/>.

Plain Jekyll with the `minima` theme, so a new post is one markdown file — no build step, no
toolchain, nothing to install locally.

## Adding a post

1. Create `_posts/YYYY-MM-DD-your-slug.md`.
2. Front matter — the `title` becomes the page heading, `permalink` fixes the URL:

   ```yaml
   ---
   layout: post
   title: "Your title"
   date: 2026-09-14
   categories: [hardware]
   tags: [asic, reverse-engineering]
   permalink: /your-slug/
   ---
   ```

3. Write the body in markdown. The post appears at
   `https://sraghup7.github.io/blogs/your-slug/` once Pages rebuilds (about a minute after a push).

## Figures and video

* Images: `assets/img/<name>.png`, referenced as
  `![alt text]({{ site.baseurl }}/assets/img/<name>.png)`.
* Video: `assets/video/<name>.mp4`, embedded as

  ```html
  <video controls preload="metadata" style="width:100%">
    <source src="{{ site.baseurl }}/assets/video/<name>.mp4" type="video/mp4">
  </video>
  ```

Use the `{{ site.baseurl }}` form rather than a bare `/assets/...` path: the site is served from a
subdirectory (`/blogs`), and absolute paths without the baseurl resolve to the user site root and 404.

## Previewing

Pushing is the fastest preview — Pages rebuilds on every push to `main`. To render locally you need
Ruby plus `gem install github-pages`, then `bundle exec jekyll serve`; nothing here requires it.

## Layout

```
_config.yml            site settings: title, baseurl, theme, permalink style
index.md               the home page (layout: home lists every post automatically)
_posts/                one markdown file per post
assets/img/            figures
assets/video/          video
```
