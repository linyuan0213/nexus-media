import { html } from "../../utility/lit-core.min.js";
import { CustomElement } from "../../utility/utility.js";

export class CustomPlexLibraryImg extends CustomElement {

  static properties = {
    img_src_list: { attribute: "img-src-list" },
    _loading: { state: true },
  };

  constructor() {
    super();
    this._loading = true;
  }

  firstUpdated() {
    this._init();
  }

  _init() {
    const canvas = this.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    // 设置背景色为黑色
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const IMAGES = (this.img_src_list || "").split(",").filter(s => s.trim());
    const POSTER_WIDTH = 150;
    const POSTER_HEIGHT = 252;
    const MARGIN_WIDTH = 8;
    const MARGIN_HEIGHT = 4;
    const REFLECTION_HEIGHT = POSTER_HEIGHT / 2;
    const REFLECTION_SHOW_HEIGHT = 100;

    const drawImageWithReflection = (img, index) => {
      const x = MARGIN_WIDTH * index + POSTER_WIDTH * (index - 1);
      const y = MARGIN_HEIGHT;

      ctx.drawImage(img, x, y, POSTER_WIDTH, POSTER_HEIGHT);

      ctx.save();
      ctx.translate(0, canvas.height);
      ctx.scale(1, -1);
      ctx.drawImage(
        img,
        0,
        0,
        img.width,
        img.height,
        x,
        REFLECTION_SHOW_HEIGHT - REFLECTION_HEIGHT,
        POSTER_WIDTH,
        REFLECTION_HEIGHT
      );

      const gradient = ctx.createLinearGradient(
        0,
        REFLECTION_SHOW_HEIGHT - REFLECTION_HEIGHT,
        0,
        REFLECTION_HEIGHT
      );
      gradient.addColorStop(0, "rgba(0, 0, 0, 1)");
      gradient.addColorStop(1, "rgba(0, 0, 0, 0.3)");
      ctx.fillStyle = gradient;
      ctx.fillRect(x, 0, POSTER_WIDTH, REFLECTION_SHOW_HEIGHT);

      ctx.restore();
    };

    const loadImage = (src) => {
      return new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = src;
      });
    };

    const loadImages = async () => {
      // 最多4个
      const sources = IMAGES.slice(0, 4);
      if (sources.length === 0) {
        this._loading = false;
        return;
      }
      // 并行加载
      const images = await Promise.all(sources.map(loadImage));
      let drawnCount = 0;
      images.forEach((img) => {
        if (img) {
          drawnCount++;
          drawImageWithReflection(img, drawnCount);
        }
      });
      this._loading = false;
    };

    loadImages();
  }

  render() {
    return html`
      <style>
        :host {
          display: block;
          position: relative;
        }
        .shimmer {
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, #1a1a1a 25%, #2a2a2a 50%, #1a1a1a 75%);
          background-size: 200% 100%;
          border-radius: 0.75rem;
          animation: shimmer 1.5s infinite;
          pointer-events: none;
        }
        .shimmer.hidden {
          display: none;
        }
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        canvas {
          display: block;
          border-radius: 0.75rem;
        }
      </style>
      <div class="shimmer ${this._loading ? "" : "hidden"}"></div>
      <canvas width="640" height="360" class="w-100"></canvas>
    `;
  }
}

window.customElements.define("custom-plex-library-img", CustomPlexLibraryImg);
