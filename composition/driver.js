/**
 * GSAP scene driver — composition/driver.js
 *
 * Drives a single 1920x1080 scene for the full narration duration.
 * Animation rules (from the visual brief):
 *   • Image fit: contain on a blurred/solid backdrop (no cropping unless fill).
 *   • Never upscale small images past 1.5x.
 *   • Crossfade 0.3–0.5 s on image change.
 *   • Slow zoom/pan: animate ONLY transform & opacity, max 5% scale.
 *   • Something on screen within 0.5 s of scene start.
 *   • Last reveal held at least 1.5 s.
 *   • Scenes hand over sequentially (no overlapping layouts).
 *   • Text ≥ 20 px; contrast ≥ 4.5:1 (authored in template.css).
 *   • Fonts declared via @font-face from a local file.
 *
 * Consumes window.__SCENE_CONFIG__ (injected by compose.py):
 *   {
 *     scene_index, duration, fit_mode, backdrop, assets: [{src, cue_word, start, end, fit}],
 *     text: [{html, x, y, start, end}], lowerThird: {kicker,title,show_seconds},
 *     titleCard, endCard, fonts: [{family, url}]
 *   }
 */
(function () {
  const ROOT = document.getElementById("root");
  const W = 1920, H = 1080;
  let tl;

  function el(tag, cls) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("failed to load " + src));
      img.src = src;
    });
  }

  function cappedScale(img, containerW, containerH, fit) {
    if (fit === "fill") return 1;
    const scaleW = containerW / img.naturalWidth;
    const scaleH = containerH / img.naturalHeight;
    const scale = Math.min(scaleW, scaleH, 1.5);
    return Math.max(scale, 0.15);
  function initScene(cfg) {
    if (!cfg) return;

    if (cfg.fonts && cfg.fonts.length) {
      const style = document.createElement("style");
      style.textContent = cfg.fonts
        .map(
          (f) =>
            `@font-face { font-family: "${f.family}"; src: url("${f.url}"); font-display: swap; }`
        )
        .join("\n");
      document.head.appendChild(style);
    }

    tl = gsap.timeline({ paused: true });
    const endTime = cfg.duration || 10;

    const backdrop = el("div", "backdrop");
    ROOT.appendChild(backdrop);
    if (cfg.backdrop) {
      const bImg = el("img");
      bImg.src = cfg.backdrop;
      backdrop.appendChild(bImg);
      tl.fromTo(
        bImg,
        { opacity: 0 },
        { opacity: 1, duration: 0.3, ease: "power2.out" },
        0
      );
    }

    const wrap = el("div", "content-wrap");
    ROOT.appendChild(wrap);

    const assets = (cfg.assets || []).slice().sort((a, b) => a.start - b.start);
    assets.forEach((asset, idx) => {
      const img = el("img", "content-img");
      img.setAttribute("data-fit", asset.fit || cfg.fit_mode || "contain");
      img.alt = "";
      wrap.appendChild(img);
      gsap.set(img, { opacity: 0, scale: 1, x: 0, y: 0 });

      const showAt = Math.max(0, asset.start);
      const holdUntil = asset.end != null ? asset.end : endTime;

      loadImage(asset.src).then(() => {
        const s = cappedScale(img, W, H, img.dataset.fit);
        gsap.set(img, {
          width: img.naturalWidth * s,
          height: img.naturalHeight * s,
        });

        tl.to(img, { opacity: 1, duration: 0.35, ease: "power2.out" }, showAt);

        const panX = (asset.pan_x || 0) * W;
        const panY = (asset.pan_y || 0) * H;
        const zoomEnd = 1 + (asset.zoom || 0.03);
        tl.to(
          img,
          {
            scale: s * zoomEnd,
            x: -panX,
            y: -panY,
            duration: holdUntil - showAt,
            ease: "none",
          },
          showAt + 0.35
        );

        const next = assets[idx + 1];
        if (next) {
          tl.to(
            img,
            { opacity: 0, duration: 0.35, ease: "power2.in" },
            Math.max(0, next.start - 0.35)
          );
        }
      });
    });

    ; (cfg.text || []).forEach((tx) => {
      const d = el("div", "text-layer cue-word");
      d.innerHTML = tx.html;
      d.style.left = (tx.x ?? 50) + "px";
      d.style.top = (tx.y ?? 50) + "px";
      if (tx.font_size) d.style.fontSize = tx.font_size + "px";
      if (tx.color) d.style.color = tx.color;
      ROOT.appendChild(d);
      gsap.set(d, { opacity: 0 });
      tl.to(d, { opacity: 1, duration: 0.3, ease: "power2.out" }, Math.max(0, tx.start));
      if (tx.end != null) {
        tl.to(d, { opacity: 0, duration: 0.3, ease: "power2.in" }, Math.max(0, tx.end));
      }
    });

    if (cfg.lowerThird && cfg.lowerThird.show_seconds > 0) {
      const lt = el("div", "lower-third");
      lt.innerHTML = `<div class="kicker">${escapeHtml(cfg.lowerThird.kicker || "")}</div><div class="title">${escapeHtml(cfg.lowerThird.title || "")}</div>`;
      ROOT.appendChild(lt);
      gsap.set(lt, { opacity: 0, y: 30 });
      tl.to(lt, { opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }, 0);
      tl.to(
        lt,
        { opacity: 0, y: 30, duration: 0.4, ease: "power2.in" },
        Math.min(cfg.lowerThird.show_seconds, 2)
      );
    }

    if (cfg.titleCard) {
      const tc = el("div", "title-card");
      tc.innerHTML = `<div class="big">${escapeHtml(cfg.titleCard.title || "")}</div><div class="sub">${escapeHtml(cfg.titleCard.sub || "")}</div>`;
      ROOT.appendChild(tc);
      const tDur = cfg.titleCard.duration || 3;
      tl.fromTo(tc, { opacity: 0 }, { opacity: 1, duration: 0.5 }, 0);
      tl.to(tc, { opacity: 0, duration: 0.5 }, tDur - 0.5);
    }

    if (cfg.endCard) {
      const ec = el("div", "end-card");
      ec.innerHTML = `<div class="big">${escapeHtml(cfg.endCard.title || "")}</div><div class="sub">${escapeHtml(cfg.endCard.sub || "")}</div>`;
      ROOT.appendChild(ec);
      const eStart = endTime - (cfg.endCard.duration || 3);
      tl.fromTo(ec, { opacity: 0 }, { opacity: 1, duration: 0.5 }, eStart);
    }

    tl.to({}, { duration: 0.01 }, endTime);
    tl.play();
    window.__SCENE_DURATION__ = endTime;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();

  }
