---
name: colab-flux
description: Consistent product, brand and marketplace-listing pictures with FLUX 3 Image Klein (Black Forest Labs, open weights) on a Google Colab GPU that is started for the job and stopped right after, via the fluxx CLI. Use when someone wants product shots, catalog or listing images, lifestyle scenes, social posts or ad visuals that look like the same brand every time - the same product, the same light, the same feel - without paying per image to an image API. Also makes marketplace listing packs for Amazon, Etsy, eBay and Shopify: a pure-white main image to Amazon's rules, the standard shot set per site, and drafted titles, bullets and tags within each site's limits. Each business gets a brand profile (what they sell, their look, what to avoid, reference photos of the product) that learns from their good/bad feedback. Renders several candidates per shot and an on-GPU judge keeps the best; outputs a high-definition PNG (~4 MP) and a medium JPEG (1024 px) per shot; keeps the GPU warm a few minutes for follow-ups. Also covers first-time setup (Google sign-in for Colab, Hugging Face license and token), changing a brand's style, and the fluxx commands. Invocable as /colab-flux.
---

# colab-flux

FLUX 3 Image Klein on a rented Colab GPU, driven by `fluxx`. A `fluxx gen` starts the best free GPU (H100, then G4, then A100) ->
installs diffusers -> downloads and loads FLUX 3 and a judge model -> renders every shot (best of
several, judged) -> downloads the pictures -> keeps the GPU warm for a few minutes for follow-ups,
then stops it. Batch every shot you can into one call.

What makes the pictures consistent is the **brand profile**, not luck:

- **product references**: real photos of the product, passed to FLUX 3 as reference images on
  every shot so the product keeps its shape, label and colors (up to 10 references)
- **style**: one paragraph of concrete photographic language appended to every scene
- **avoid**: what never appears
- **seed**: fixed per brand, so the same scene renders the same way again
- **feedback**: every shot is logged; `fluxx rate` records what the person liked and why, and
  you fold the pattern back into the style

Everything lives in `~/colab-flux/brands/<name>/`: `brand.json`, `refs/`, `history.jsonl`,
`shots/<time>/`.

## 1. First use: check setup

Run `fluxx doctor` (if `fluxx` is not found, run `sh <this skill's folder>/install.sh` first). It prints
`ok` / `TODO` lines. Walk the person through each TODO, in plain words, one at a time:

| TODO | What the person does | Notes |
|---|---|---|
| Colab CLI not installed | nothing: you run `sh install.sh` from this skill's folder | installs `uv` and the official Colab CLI |
| not signed in to Google | runs `fluxx login` **in their own terminal** | a browser opens for Google sign-in. You cannot do this for them |
| compute units | buys Colab Pro or compute units at https://colab.research.google.com/signup | the A100 is not on the free tier |
| Hugging Face (optional) | nothing by default: without a token fluxx downloads from a public mirror after checking every weight file's sha256 against the official repo. For the official repo: `fluxx login` opens the FLUX 3 page, they click agree, create a Read token and paste it at the hidden prompt | free. Never ask them to paste the token into the chat |
| no brands | nothing: you do the brand interview below | |

`fluxx login` asks for the token with a hidden prompt, so it needs a real terminal: in Claude Code
tell them to open a terminal tab and run it there (Codex, same). When they say it is done, run
`fluxx doctor` again.

## 2. Brand interview (once per business)

Ask these in **one** message, short, with examples so it takes a minute to answer:

1. What is the business, and what product(s) should appear? (e.g. "hand-poured soy candles in amber jars")
2. Who buys it, and where will the pictures be used? (Shopify, Amazon, Etsy, Instagram, ads, print)
3. The look, in a few words or a brand they admire. (e.g. "calm, warm, Scandinavian, like Aesop")
4. Anything that must never appear? (people, text, competitor items, clutter, certain colors)
5. Photos of the product: file paths or drag them in. A plain, well-lit photo per product works best.

Then turn the answers into the profile. Translate adjectives into words a photographer would
use, because that is what FLUX follows. "Calm and warm" becomes "soft diffused window light from
the left, warm neutral palette of oat, sand and terracotta, matte linen and pale oak surfaces,
shallow depth of field, generous negative space, editorial product photography".

```bash
fluxx brand new acme-candles --business "Acme, hand-poured soy candles in amber glass jars" \
  --style "soft diffused window light from the left, warm neutral palette ..." \
  --avoid "people, hands, written text other than the jar label, clutter" --aspect 4:5
fluxx brand ref acme-candles /path/to/jar-front.jpg            # role: product (default)
fluxx brand ref acme-candles /path/to/moodboard.jpg --role style
```

Aspect by destination: Amazon/Shopify product grid 1:1, Instagram feed 4:5, stories/reels 9:16,
web hero 16:9, Etsy 4:3 or 1:1. The brand's aspect is the default; `--aspect` overrides per run.
Show the person the profile you wrote (`fluxx brand show NAME`) and ask if it sounds like them.

## 3. Making pictures

1. `fluxx brand show NAME`: read the profile **and the recent feedback** before you write anything.
2. Write the scenes. One short concrete line each, about the scene only. The brand style,
   avoid list and reference roles are added automatically, and FLUX 3's own prompt upsampler (a
   9B model on the GPU) expands each line into a full caption, so do not spend tokens writing long
   prompts. Good: `the jar on a sunlit oak windowsill, morning, a sprig of dried eucalyptus beside it`.
3. Collect every shot the person might want into **one** call (startup is the expensive part):
   ```bash
   fluxx gen -b acme-candles -n 2 "scene one" "scene two" "scene three"
   fluxx gen -b acme-candles --from shots.txt          # one scene per line, # comments ok
   ```
   A scene can set its own shape with a prefix, so one run can mix formats:
   `16:9 | the jar on a sunlit windowsill, space on the left for a headline`.
   A cold start takes ~4 minutes, then ~45 s per 4 MP render. In Claude Code run it with
   `run_in_background`; in Codex let it run. It prints one picture path per line on stdout;
   progress, each shot's judge score and defects, and the compute-unit cost go to stderr.
   When a person is in a scene using the product, say how: "holding the phone's handset to her
   ear, its cord trailing out of frame; the phone base not visible". FLUX draws the product the way
   the reference shows it, so a lifted part tends to appear twice (in testing, a held handset plus
   one still on the phone, even when the prompt said the cradle was empty). Framing the rest of the
   product out of the picture fixed it.
4. **Best of N, judged on the GPU.** Each shot renders up to `--candidates` images (default 3).
   A vision-language judge (Qwen3.5-9B, on the same GPU) checks each against the brief, the product
   references and the avoid list (anatomy, duplicated objects, product fidelity, stray text,
   appeal), keeps the best, and stops early when one scores 9+ with no defects. The others come
   back small in `alts/`, so the person can still pick one.
5. Look at the `_md.jpg` files yourself too (they are small), especially any shot whose stderr line
   lists defects or scores below 7. Say what is wrong with it rather than presenting it as done.
   Then give the person the folder and the paths.
6. **The GPU stays warm afterwards** (`--keep`, default 5 minutes) with the models loaded, so a
   follow-up `fluxx gen` with the same setup starts rendering at once instead of after ~4 minutes.
   Right after presenting, ask: "The GPU is still warm for N minutes (about X compute units if it
   sits idle). Want more or changes? Otherwise I'll shut it down." If they are done, run
   `fluxx stop`. If they say nothing, it stops by itself. If they ask to keep it longer, pass
   `--keep 15` on the next run, or save a new default with `fluxx config keep_minutes 15`.
   `--keep 0` stops the GPU at the end of the run.

Flags: `--gpu H100,G4,A100` cards to try, best first, retried until one is free · `--wait-minutes N` stop retrying after N minutes · `-n N` variations per scene (seeds seed..seed+N-1) · `--candidates K` renders per shot, best
kept (1-8) · `--keep MIN` warm minutes afterwards · `--draft` 1 MP medium only, one candidate,
faster, for exploring a new direction · `--aspect W:H` · `--ref PATH` one-off extra product photo ·
`--no-refs` · `--seed S` · `--no-upsample` when the scenes are already full captions (skips a
19 GB download) · `--out DIR`.

Outputs per shot: `<id>_hd.png` (about 4 MP, e.g. 2048x2048, for print, zoom and hero images) and
`<id>_md.jpg` (1024 px long side, for listings, web and social).

## 4. Marketplace listings (Amazon, Etsy, eBay, Shopify)

When the pictures are for selling a product online, use `fluxx listing` instead of `gen`. One run makes
the standard set of six square 4 MP shots, exports a folder per marketplace with that site's order,
names and sizes, and drafts the listing copy on the GPU (the judge model writes it, so no Claude tokens):

```bash
fluxx listing -b acme-candles --product "hand-poured soy candle in an amber glass jar with a wooden lid" \
  --notes "8 oz, 50-hour burn, cotton wick, scent: cedar and smoke, made in Oregon" --for amazon,etsy
```

| Shot (role) | What | Brand look |
|---|---|---|
| `main` | product alone on pure white, centered | none: fluxx then makes the background exactly RGB 255 and scales the product to fill 85% of the frame (Amazon's main-image rule) |
| `angle` | three-quarter view on white | none |
| `detail` | close-up of materials and finish | none |
| `lifestyle` | in use, in a setting that fits the buyers | yes |
| `scale` | next to everyday objects, so the size is obvious | yes |
| `gift` | in hands or as a gift, no face | yes |

Output in the run folder under `markets/<site>/`:

| Site | Pictures | Copy (`listing.md` + `copy.json`), limits enforced by fluxx |
|---|---|---|
| amazon | `MAIN.jpg`, `PT01.jpg`... 2048 px | title 75 chars (the limit since July 2026), item highlights 125, 5 bullets of 200, description 2000, search terms 250 bytes |
| etsy | `01.jpg`... 2048 px, a styled shot first (it is the search thumbnail) | title 140, 13 tags of 20 chars, description |
| ebay | `01.jpg`... 1600 px | title 80, item specifics, description |
| shopify | `01.jpg`... 2048 px | title 70, SEO title 60, SEO description 160, description, tags |

Rules for the agent:
- **Facts come from the seller.** Ask for size, materials, what is included and care before the run, and
  pass them in `--notes`. The copy model is told never to invent facts, but read `listing.md` and remove
  any claim that is not in the notes or visible in the picture before the person publishes.
- **The pictures show what FLUX drew, not the real item.** For `main`, `angle` and `detail`, the product
  must match the person's real product: check it against their photos, and tell them that marketplaces
  require images to show the actual item. Lifestyle shots are where generated scenes help most.
- The finished white `main` image becomes the product reference for the later shots, so props in the
  person's own photo (a tablecloth, decorations) do not leak into lifestyle shots. Still ask for a plain,
  well-lit product photo: it is what `main` is drawn from.
- `--only main,lifestyle` makes a subset; `--no-refs --ref other.jpg` lists a different product of the
  same brand; `--for etsy` limits the sites.

## 5. Learning what they like

The profile gets better only if you close the loop. Every time the person reacts to a picture:

```bash
fluxx rate 02-jar-on-oak-windowsill-v1 good "loves the low morning light"
fluxx rate 03-jar-in-bathroom-v2 bad "too busy, the towel steals focus"
```

When two or more ratings point the same way, edit `brand.json` (it is plain JSON; edit it with
your file tools): sharpen `style`, extend `avoid`, add a dated line to `notes` saying what changed
and why. When the same **defect** comes back (a doubled part, a wrong color, a missing label),
add a one-line rule to `checks`, e.g. `"Exactly one telephone handset in the whole picture"`.
The judge then counts and verifies that rule on every candidate from now on; a general score
alone missed exactly this kind of defect in testing. Tell the person in one line ("I added 'low morning light' to your style and dropped
props near the jar"). A shot they love can become a style reference:
`fluxx brand ref NAME <path>_hd.png --role style` (references are capped at 10 in total; FLUX 3
treats style references as look only, not content).

**Changing the style on request** ("make it darker and moodier", "we're rebranding to pastel"):
rewrite `style` in `brand.json`, keep the old one in `notes` with the date so they can go back,
remove style references that no longer fit, and offer a quick `--draft` run of 3-4 known scenes so
they see the new look before a full batch. For a second, separate look (e.g. a holiday campaign),
create another brand with the same product references instead of overwriting.

## Rules

- **One call, many shots.** Never loop `fluxx gen` per picture. A cold start (GPU, ~60 GB of models,
  loading) costs ~4 minutes. Follow-ups inside the warm window skip it.
- **The GPU always stops.** On failure `fluxx` stops it at once. On success it stays warm for
  `--keep` minutes and a detached watchdog then stops it, even if `fluxx` or the agent is gone.
  During a run the watchdog caps it at `--max-minutes` (default 60). If a run ends with
  `NOT CONFIRMED STOPPED`, run `fluxx stop` then `fluxx status` immediately.
- **No secrets in chat.** The Hugging Face token is typed into `fluxx login`'s hidden prompt only.
  It travels to the person's own Colab VM, which deletes it from disk once read and is wiped on stop.
- **Their pictures stay theirs.** Product photos are uploaded only to their own Colab VM.
- **License.** FLUX 3 Image Klein is under the FLUX Kommunity License: free, including commercial
  use of the pictures, for individuals and businesses under US$5M yearly revenue; larger
  businesses need a license from Black Forest Labs (https://bfl.ai). Mention this once during
  onboarding if the business might be larger.

## Commands

```bash
fluxx doctor                       # what is set up, what is missing
fluxx login                        # Google sign-in + Hugging Face token (person runs it, needs a terminal)
fluxx brand new|show|list|ref ...  # brand profiles
fluxx gen -b NAME [...] scenes...  # render (reuses a warm GPU)
fluxx listing -b NAME --product .. --notes .. [--for amazon,etsy,ebay,shopify]  # marketplace pack
fluxx rate SHOT good|bad "why"     # feedback
fluxx config [keep_minutes|candidates N]   # defaults: 5 warm minutes, 3 candidates
fluxx status                       # Colab sessions and compute-unit balance
fluxx stop                         # stop a leftover GPU session (always safe)
fluxx selftest                     # offline check, no Colab call
```

Environment: `COLAB_FLUX_HOME` (default `~/colab-flux`), `FLUXX_GPU` (default `H100,G4,A100`: best
to worst, tried in order. A card Colab answers "Service Unavailable" for, or one with under 60 GB of
GPU memory (checked with nvidia-smi on the VM, then stopped), is skipped for the next. When every card is busy, `fluxx` waits and goes round the list again (30 s,
doubling to 10 min between rounds) until one is free: a run started at a busy hour simply starts later.
`--wait-minutes N` caps the waiting; a card refused for another reason (not on the plan) never loops. The pipeline peaks
at ~56 GB, so T4 and L4 never qualify. `--gpu` sets it per run, e.g. `--gpu A100` to save compute
units: faster cards cost more per hour), `FLUXX_MODEL`, `FLUXX_MIRROR` (empty disables the mirror), `HF_TOKEN`.
