import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

/**
 * 图片懒加载 Intersection Observer 配置
 */
const imageObserverOptions = {
  root: null,
  rootMargin: '200px', // 提前 200px 开始加载（全方向）
  threshold: 0
};

/**
 * 全局图片观察器
 */
let imageObserver = null;
if ('IntersectionObserver' in window) {
  imageObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target;
        const realSrc = img.dataset.src;
        if (realSrc) {
          img.src = realSrc;
          img.removeAttribute('data-src');
        }
        observer.unobserve(img);
      }
    });
  }, imageObserverOptions);
}

export class CustomImg extends CustomElement {

  static properties = {
    img_src: { attribute: "img-src" },
    img_noimage: { attribute: "img-noimage" },
    img_class: { attribute: "img-class" },
    img_style: { attribute: "img-style" },
    img_ratio: { attribute: "img-ratio" },
    div_style: { attribute: "div-style" },
    img_placeholder: { attribute: "img-placeholder" },
    img_error: { attribute: "img-error" },
    img_src_list: { type: Array },
    lazy: {},
    _placeholder: { state: true },
    _timeout_update_img: { state: true },
  };

  constructor() {
    super();
    this.img_noimage = Golbal.noImage;
    this.lazy = "0";
    this.img_placeholder = "1";
    this.img_error = "1";
    this.img_src_list = [];
    this._timeout_update_img = 0;
    this._placeholder = true;
    this._observerAttached = false;
  }

  willUpdate(changedProperties) {
    if (changedProperties.has("img_src")) {
      // 懒加载时显示占位符，非懒加载时直接显示图片
      this._placeholder = this.lazy === "1";
    }
    if (changedProperties.has("img_src_list")) {
      this._timeout_update_img = 0;
      this._update_img();
    }
  }

  firstUpdated() {
    this._query_img = this.querySelector("img");
    // 如果不是懒加载，直接加载图片
    if (this.lazy !== "1") {
      this._placeholder = false;
    }
    this._setupLazyLoading();
  }

  updated() {
    // 每次更新后重新设置懒加载（如果 lazy 属性改变）
    if (this.lazy === "1" && !this._observerAttached && this._query_img) {
      this._setupLazyLoading();
    }
  }

  _setupLazyLoading() {
    if (this.lazy === "1" && this._query_img && imageObserver) {
      // 将真实 URL 存入 data-src
      if (this.img_src && !this._query_img.dataset.src) {
        this._query_img.dataset.src = this.img_src;
        imageObserver.observe(this._query_img);
        this._observerAttached = true;
      }
    } else if (this.lazy !== "1" && this._query_img) {
      // 非懒加载，确保图片显示
      this._placeholder = false;
    }
  }

  _update_img() {
    if (this.img_src_list) {
      if (this.img_src_list.length > 1) {
        this._query_img.classList.remove("lit-custom-img-carousel-show");
        setTimeout(() => {
          this.img_src = this.img_src_list[this._timeout_update_img];
          this._timeout_update_img ++;
          if (this._timeout_update_img >= this.img_src_list.length) {
            this._timeout_update_img = 0;
          }
        }, 1000);
      } else if (this.img_src_list.length == 1) {
        this.img_src = this.img_src_list[0];
      }
    }
  }

  /**
   * 智能选择图片尺寸
   * 根据容器大小选择最合适的 TMDB 图片尺寸
   * 只对 TMDB 图片进行尺寸优化，豆瓣/Bangumi 图片保持不变
   */
  _getOptimalImageUrl() {
    if (!this.img_src) return "";
    
    // 非 TMDB 图片（豆瓣、Bangumi 等）直接返回原URL
    if (this.img_src.includes('/img/douban/') || this.img_src.includes('/img/bgm/')) {
      return this.img_src;
    }
    
    // 如果已经是小尺寸，不再处理
    if (this.img_src.includes('/w92/') || this.img_src.includes('/w185/')) {
      return this.img_src;
    }
    
    // 获取容器宽度来估算需要的图片尺寸
    const containerWidth = this.offsetWidth || 300;
    
    // TMDB 尺寸: w92, w154, w185, w342, w500, w780, original
    let targetSize = 'w500';
    if (containerWidth <= 100) targetSize = 'w92';
    else if (containerWidth <= 200) targetSize = 'w185';
    else if (containerWidth <= 350) targetSize = 'w342';
    else if (containerWidth <= 600) targetSize = 'w500';
    else targetSize = 'w780';
    
    // 替换 URL 中的尺寸标识（只对 TMDB 图片）
    return this.img_src.replace(/\/w\d+\//, `/${targetSize}/`)
                       .replace(/\/original\//, `/${targetSize}/`);
  }

  render() {
    // 优化图片 URL
    const optimizedSrc = this._getOptimalImageUrl();
    
    // 懒加载时，使用占位符，真实 URL 存入 data-src
    const isLazy = this.lazy === "1";
    // 非懒加载时，如果没有优化后的URL或为空，使用默认图片
    const effectiveSrc = optimizedSrc || this.img_noimage;
    const imgSrc = isLazy ? "" : effectiveSrc;
    const dataSrc = isLazy ? effectiveSrc : "";
    
    return html`
      <div class="placeholder-glow${this.img_ratio ? " ratio" : ""}"
          style=${(this.img_ratio ? "--tblr-aspect-ratio:" + this.img_ratio + ";" : "") + (this.div_style ?? "")}>
        <div ?hidden=${!this._placeholder || this.img_placeholder != "1"}
             class="placeholder rounded-0 ${this.img_class}"
             style=${this.img_style}></div>
        <img ?hidden=${this._placeholder && !isLazy}
             alt=""
             class=${this.img_class}
             style=${this.img_style}
             src=${imgSrc}
             data-src=${dataSrc}
             loading=${isLazy ? "lazy" : "eager"}
             decoding="async"
             @error=${() => {
               if (this.img_error == "1") {
                 this.img_src = this.img_noimage;
                 this._placeholder = false;
               }
             }}
             @load=${() => {
               this._placeholder = false;
               // 图像渐入
               if (this.img_src_list && this.img_src_list.length > 0) {
                 this._query_img.classList.add("lit-custom-img-carousel");
                 setTimeout(() => {
                   this._query_img.classList.add("lit-custom-img-carousel-show");
                   setTimeout(() => {
                     this._update_img();
                   }, 7000);
                 }, 100);
               }
             }}/>
      </div>
    `;
  }

}

window.customElements.define("custom-img", CustomImg);