---
name: colab-flux
description: Consistent product and brand pictures with FLUX 3 Image Klein (Black Forest Labs, open weights) on a Google Colab GPU that is started for the job and stopped right after, via the fluxx CLI. Use when someone wants product shots, catalog or listing images, lifestyle scenes, social posts or ad visuals that look like the same brand every time - the same product, the same light, the same feel - without paying per image to an image API. Each business gets a brand profile (what they sell, their look, what to avoid, reference photos of the product) that learns from their good/bad feedback. Outputs a high-definition PNG (~4 MP) and a medium JPEG (1024 px) per shot. Also covers first-time setup (Google sign-in for Colab, Hugging Face license and token), changing a brand's style, and the fluxx commands. Invocable as /colab-flux.
---

# colab-flux

FLUX 3 Image Klein on a rented Colab GPU, driven by `fluxx`. One `fluxx gen` = one GPU lifetime:
start an A100 -> install diffusers -> download and load FLUX 3 -> render every shot -> download
the pictures -> stop the GPU. Nothing stays running between jobs, so batch every shot you can
into one call.

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
| Hugging Face token / license | in the same `fluxx login`: opens the FLUX 3 page, clicks agree, creates a Read token, pastes it at the hidden prompt | free. Never ask them to paste the token into the chat |
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
   It takes several minutes. In Claude Code run it with `run_in_background`; in Codex let it run.
   It prints one picture path per line on stdout. Progress and the compute-unit cost go to stderr.
4. Look at the `_md.jpg` files yourself before presenting (they are small). Reject shots where the
   product changed shape, the label is garbled, or something from the avoid list slipped in, and
   say so. Then give the person the folder and the paths.

Flags: `-n N` variations per scene (seeds seed..seed+N-1) · `--draft` 1 MP medium only, faster,
for exploring a new direction · `--aspect W:H` · `--ref PATH` one-off extra product photo ·
`--no-refs` · `--seed S` · `--no-upsample` when the scenes are already full captions (skips a
19 GB download) · `--out DIR`.

Outputs per shot: `<id>_hd.png` (about 4 MP, e.g. 2048x2048, for print, zoom and hero images) and
`<id>_md.jpg` (1024 px long side, for listings, web and social).

## 4. Learning what they like

The profile gets better only if you close the loop. Every time the person reacts to a picture:

```bash
fluxx rate 02-jar-on-oak-windowsill-v1 good "loves the low morning light"
fluxx rate 03-jar-in-bathroom-v2 bad "too busy, the towel steals focus"
```

When two or more ratings point the same way, edit `brand.json` (it is plain JSON; edit it with
your file tools): sharpen `style`, extend `avoid`, add a dated line to `notes` saying what changed
and why. Tell the person in one line ("I added 'low morning light' to your style and dropped
props near the jar"). A shot they love can become a style reference:
`fluxx brand ref NAME <path>_hd.png --role style` (references are capped at 10 in total; FLUX 3
treats style references as look only, not content).

**Changing the style on request** ("make it darker and moodier", "we're rebranding to pastel"):
rewrite `style` in `brand.json`, keep the old one in `notes` with the date so they can go back,
remove style references that no longer fit, and offer a quick `--draft` run of 3-4 known scenes so
they see the new look before a full batch. For a second, separate look (e.g. a holiday campaign),
create another brand with the same product references instead of overwriting.

## Rules

- **One call, many shots.** Never loop `fluxx gen` per picture. Startup (GPU, ~40 GB model
  download, loading) is most of the time and cost of a run.
- **The GPU always stops.** `fluxx` stops it in a `finally` block and a watchdog stops it after
  `--max-minutes` (default 60) even if `fluxx` is killed. If a run ends with
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
fluxx gen -b NAME [...] scenes...  # render, one GPU lifetime
fluxx rate SHOT good|bad "why"     # feedback
fluxx status                       # Colab sessions and compute-unit balance
fluxx stop                         # stop a leftover GPU session (always safe)
fluxx selftest                     # offline check, no Colab call
```

Environment: `COLAB_FLUX_HOME` (default `~/colab-flux`), `FLUXX_GPU` (default `A100`, the 80 GB
card; the model plus upsampler need about 40 GB), `FLUXX_MODEL`, `HF_TOKEN`.
