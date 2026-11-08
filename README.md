# colab-flux

Product and brand pictures that look the same every time, made by **FLUX 3 Image Klein** (Black
Forest Labs' open-weights model) on your own Google Colab GPU. It is a skill for Claude Code and
Codex: you ask your agent for pictures in plain words, it handles the rest, and the GPU is
switched off the moment the pictures are downloaded. There is no per-image API bill; a run costs
Colab compute units.

- **Consistent**: your real product photos go in as reference images, and every shot follows
  your brand's style and seed
- **Learns your taste**: tell the agent what you like and dislike, and it refines your brand profile
- **Two sizes per shot**: high definition PNG (about 4 MP, e.g. 2048x2048) and a medium JPEG
  (1024 px) for listings and social
- **Nothing left running**: one command = one GPU lifetime, with a watchdog as a safety net

## Install

**Easiest: ask your agent.** Paste this into Claude Code or Codex:

> Install this skill: https://github.com/Neoo-Blue/colab-flux

> **Agents:** run `curl -fsSL https://raw.githubusercontent.com/Neoo-Blue/colab-flux/main/install.sh | sh`
> (or clone this repo and run `sh install.sh`), then follow `SKILL.md` section 1 with the person:
> they must run `fluxx login` themselves in a terminal. Never ask them to paste a token into chat.

**Or in a terminal:**

```bash
curl -fsSL https://raw.githubusercontent.com/Neoo-Blue/colab-flux/main/install.sh | sh
fluxx login
```

The installer puts the skill where Claude Code (`~/.claude/skills`) and Codex/other agents
(`~/.agents/skills`, `~/.codex/skills`) find it, links `fluxx` into `~/.local/bin`, and installs
[uv](https://docs.astral.sh/uv/) and the official [Colab CLI](https://pypi.org/project/google-colab-cli/).
Runs on macOS and Linux; on Windows, inside WSL2 (`wsl --install -d Ubuntu`).

### What you need

| | Why | Cost |
|---|---|---|
| A Google account with **Colab Pro** or compute units | the A100 GPU | Colab Pro is about $10/month with 100 compute units |
| A free **Hugging Face** account, with the [FLUX 3 license](https://huggingface.co/black-forest-labs/flux-3-image-klein) accepted and a Read token | the model weights are gated | free |

`fluxx login` walks through both: a browser opens for Google, then it shows the two Hugging Face
links and asks for the token at a hidden prompt. `fluxx doctor` shows what is still missing.

## Use

Ask your agent, for example: *"Make product photos for my candle shop: the jar on a windowsill,
in a bathroom, and on a gift table, two of each."* The first time, it asks five quick questions
about your business, look and product photos, and saves them as your brand. After that, every
request uses that brand. Say what you like or dislike about the results and the agent updates
the brand; say "make it moodier" and it changes the style (and keeps the old one so you can go back).

Pictures are saved in `~/colab-flux/brands/<brand>/shots/<time>/`.

The same thing by hand:

```bash
fluxx brand new my-shop --business "hand-poured soy candles" --style "soft window light, warm neutrals, oak and linen" --aspect 4:5
fluxx brand ref my-shop ~/Desktop/jar.jpg
fluxx gen -b my-shop -n 2 "the jar on a sunlit windowsill" "the jar on a gift table with ribbon"
fluxx rate 01-the-jar-on-a-sunlit-windowsill-v1 good "love the light"
```

## How it works

`fluxx gen` starts an A100 80 GB on Colab, uploads `remote_job.py`, your product photos and the
shot list, and starts the job: install diffusers, download FLUX 3 Image Klein (~11 GB), its
Qwen3-VL text encoder and its 9B prompt upsampler (~19 GB), then render every shot with the
references and a fixed seed. `fluxx` polls progress, downloads the zipped pictures, and stops the
GPU in a `finally` block. A detached watchdog stops it after `--max-minutes` even if `fluxx` is
killed. Your token is uploaded to your own VM as a file, read, and deleted; it never appears in
code or logs.

## License

Code: MIT. The model is not covered by this license: FLUX 3 Image Klein is under the
[FLUX Kommunity License](https://huggingface.co/black-forest-labs/flux-3-image-klein), free
including commercial use of outputs for individuals and businesses under US$5M yearly revenue;
larger businesses license it from [Black Forest Labs](https://bfl.ai).
