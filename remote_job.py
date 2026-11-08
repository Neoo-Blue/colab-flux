"""Runs ON the Colab VM, uploaded and started by `fluxx gen`. Not meant to run locally.

Reads /content/fluxx/spec.json, installs diffusers, loads FLUX 3 Image Klein once, renders every
shot, and writes the images plus manifest.json into /content/fluxx/out, zipped as out.zip.
Progress goes to progress.json so the local side can poll it over short `colab exec` calls.
"""
import json
import os
import subprocess
import sys
import time
import traceback
import zipfile

W = "/content/fluxx"
OUT = f"{W}/out"


def progress(**kw):
    with open(f"{W}/progress.tmp", "w") as f:
        json.dump(kw, f)
    os.replace(f"{W}/progress.tmp", f"{W}/progress.json")


def main():
    spec = json.load(open(f"{W}/spec.json"))
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()

    progress(stage="installing diffusers")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers>=0.42.1",
                    "transformers", "accelerate", "hf_xet"], check=True)
    tok = f"{W}/hf_token"
    if os.path.exists(tok):  # never printed, removed from disk once read
        os.environ["HF_TOKEN"] = open(tok).read().strip()
        os.remove(tok)
    os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"

    progress(stage="downloading and loading the model")
    import torch
    from diffusers import ModularPipeline
    from PIL import Image

    if spec["upsample"]:
        pipe = ModularPipeline.from_pretrained(spec["model"])
    else:  # captions are already complete: skip the 9B prompt upsampler (and its 19 GB download)
        blocks = ModularPipeline.from_pretrained(spec["model"]).blocks
        blocks.sub_blocks.pop("prompt_upsampler")
        pipe = blocks.init_pipeline(spec["model"])
    pipe.load_components(dtype={"vae": torch.float32, "default": torch.bfloat16})
    pipe.to("cuda")
    t_ready = time.time()

    refs = {p: Image.open(p).convert("RGB") for s in spec["shots"] for p in s["refs"]}
    results, total = [], len(spec["shots"])
    for i, shot in enumerate(spec["shots"]):
        progress(stage="rendering", done=i, total=total, ready_s=round(t_ready - t0))
        t = time.time()
        rec = {k: shot[k] for k in ("id", "scene", "seed", "width", "height")}
        try:
            kw = dict(prompt=shot["request"], width=shot["width"], height=shot["height"],
                      generator=torch.Generator().manual_seed(shot["seed"]), output=["images", "prompt"])
            if shot["refs"]:
                kw["image"] = [refs[p] for p in shot["refs"]]
            out = pipe(**kw)
            img = out["images"][0]
            rec["caption"] = out["prompt"] if isinstance(out["prompt"], str) else out["prompt"][0]
            if not shot["draft"]:
                img.save(f"{OUT}/{shot['id']}_hd.png")
                rec["hd"] = f"{shot['id']}_hd.png"
            md = img.copy()
            md.thumbnail((spec["md_side"], spec["md_side"]), Image.LANCZOS)
            md.save(f"{OUT}/{shot['id']}_md.jpg", quality=92)
            rec["md"] = f"{shot['id']}_md.jpg"
        except Exception as e:  # one bad shot must not lose the rest
            rec["error"] = f"{type(e).__name__}: {e}"[:800]
        rec["seconds"] = round(time.time() - t, 1)
        results.append(rec)

    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    json.dump({"gpu": gpu, "ready_s": round(t_ready - t0), "shots": results},
              open(f"{OUT}/manifest.json", "w"), indent=1)
    with zipfile.ZipFile(f"{W}/out.zip", "w", zipfile.ZIP_STORED) as z:  # PNG/JPEG are already compressed
        for name in os.listdir(OUT):
            z.write(f"{OUT}/{name}", name)
    progress(stage="finished", done=total, total=total, ready_s=round(t_ready - t0))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        progress(stage="failed", error=traceback.format_exc()[-3000:])
        raise
