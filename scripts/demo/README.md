# Demo video and portfolio screenshots

Requires the API on :8000 and the web app on :3000 (`make api`, `make web`), ffmpeg, Node 20.

```sh
cd scripts/demo && npm install && npx playwright install chromium
ADMIN_PASSWORD=smartsearch node warm.js      # compile every route once
ADMIN_PASSWORD=smartsearch node record.js    # raw/<scene>.webm, 1920x1080, one file per scene
bash compose.sh ../..                        # docs/demo/smartsearch-demo.mp4, -720p.mp4, -preview.gif
ADMIN_PASSWORD=smartsearch node shots.js ../../docs/portfolio   # 1440x900 retina screenshots
uv run --project ../../backend python cover.py ../..            # docs/portfolio/00-cover.png
```

Scenes, captions and speeds are the `SCENES` table in `compose.sh`; the walkthrough steps are in `record.js`.
Title cards use the storefront backdrop with a slow zoom; fonts are macOS system fonts (New York, Arial).
