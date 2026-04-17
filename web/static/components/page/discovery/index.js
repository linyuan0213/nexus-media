import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

export class PageDiscovery extends CustomElement {
  static properties = {
    discovery_type: { attribute: "discovery-type" },
    _slide_card_list: { state: true },
    _media_type_list: { state: true },
  };

  constructor() {
    super();
    this._slide_card_list = {};
    this._media_type_list = {
      "RANKING": [
        {
          type: "MOV",
          title:"正在热映",
          subtype :"dbom",
        },
        {
          type: "MOV",
          title:"即将上映",
          subtype :"dbnm",
        },
        {
          type: "TRENDING",
          title:"TMDB流行趋势",
          subtype :"tmdb",
        },
        {
          type: "MOV",
          title:"豆瓣热门电影",
          subtype :"dbhm",
        },
        {
          type: "MOV",
          title:"豆瓣电影TOP250",
          subtype :"dbtop",
        },
        {
          type: "TV",
          title:"豆瓣热门剧集",
          subtype :"dbht",
        },
        {
          type: "TV",
          title:"豆瓣热门动漫",
          subtype :"dbdh",
        },
        {
          type: "TV",
          title:"豆瓣热门综艺",
          subtype :"dbzy",
        },
        {
          type: "TV",
          title:"华语口碑剧集榜",
          subtype :"dbct",
        },
        {
          type: "TV",
          title:"全球口碑剧集榜",
          subtype :"dbgt",
        }
      ],
      "BANGUMI": [
        {
          type: "TV",
          title:"星期一",
          subtype :"bangumi",
          week :"1",
        },
        {
          type: "TV",
          title:"星期二",
          subtype :"bangumi",
          week :"2",
        },
        {
          type: "TV",
          title:"星期三",
          subtype :"bangumi",
          week :"3",
        },
        {
          type: "TV",
          title:"星期四",
          subtype :"bangumi",
          week :"4",
        },
        {
          type: "TV",
          title:"星期五",
          subtype :"bangumi",
          week :"5",
        },
        {
          type: "TV",
          title:"星期六",
          subtype :"bangumi",
          week :"6",
        },
        {
          type: "TV",
          title:"星期日",
          subtype :"bangumi",
          week :"7",
        },
      ]
    }
  }

  firstUpdated() {
    for (const item of this._media_type_list[this.discovery_type]) {
      Golbal.get_cache_or_ajax("/api/web/media/get_recommend",
          self.discovery_type + item.title,
          { "type": item.type, "subtype": item.subtype, "page": 1, "week": item.week},
          (ret) => {
            if (ret.Items) {
              this._slide_card_list = {...this._slide_card_list, [item.title]: ret.Items};
              // 自动预加载图片到缓存
              this._preloadImages(ret.Items, item.subtype);
            }
          }
       );
    }
  }

  /**
   * 批量预加载图片到本地缓存
   */
  _preloadImages(items, subtype) {
    if (!items || items.length === 0) return;
    
    // 提取图片URL和来源
    const imageUrls = [];
    const source = subtype === 'bangumi' ? 'bgm' :
                   (subtype.startsWith('db') ? 'douban' : 'tmdb');
    
    for (const item of items) {
      if (item.image && !item.image.startsWith('/img/')) {
        // 外部URL，需要预加载
        imageUrls.push(item.image);
      }
    }
    
    if (imageUrls.length === 0) return;
    
    // 调用预加载API（最多20张）
    const urlsToLoad = imageUrls.slice(0, 20);
    fetch('/img/preload', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        urls: urlsToLoad,
        source: source
      })
    }).catch(err => {
      // 静默失败，不影响用户体验
      console.debug('图片预加载失败:', err);
    });
  }

  render() {
    return html`
      <div class="container-xl">
        ${this._media_type_list[this.discovery_type]?.map((item) => ( html`
          <custom-slide
            slide-title=${item.title}
            slide-click="javascript:navmenu('recommend?type=${item.type}&subtype=${item.subtype}&week=${item.week ?? ""}&title=${item.title}')"
            lazy="normal-card"
            .slide_card=${this._slide_card_list[item.title]
              ? this._slide_card_list[item.title].map((card, index) => ( html`
                <normal-card
                  @fav_change=${(e) => {
                    Golbal.update_fav_data("get_recommend", item.subtype, (extra) => (
                      extra.Items[index].fav = e.detail.fav, extra
                    ));
                  }}
                  lazy=1
                  card-tmdbid=${card.id}
                  card-mediatype=${card.type}
                  card-showsub=1
                  card-image=${'/img?url='+card.image}
                  card-fav=${card.fav}
                  card-vote=${card.vote}
                  card-year=${card.year}
                  card-title=${card.title}
                  card-overview=${card.overview}
                  card-restype=${card.media_type}
                  class="px-2"
                ></normal-card>`))
              : Array(20).fill(html`<normal-card-placeholder></normal-card-placeholder>`)
            }
          ></custom-slide>`
        ))}
      </div>
    `;
  }
}


window.customElements.define("page-discovery", PageDiscovery);