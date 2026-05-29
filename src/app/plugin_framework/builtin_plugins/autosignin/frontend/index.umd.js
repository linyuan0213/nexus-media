/**
 * AutoSignIn 插件前端 UMD 包
 * 包含：HistoryPage 签到历史页面
 */
(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined'
    ? factory(exports, require('vue'))
    : typeof define === 'function' && define.amd
      ? define(['exports', 'vue'], factory)
      : (global = typeof globalThis !== 'undefined' ? globalThis : global || self,
         factory(global.__PLUGIN_autosignin__ = {}, global.Vue));
})(this, function (exports, Vue) {
  'use strict';

  const { h, ref, onMounted, computed } = Vue;
  const rc = (typeof window !== 'undefined' && window.requestClient) || null;
  const IconifyIcon = (typeof window !== 'undefined' && window.IconifyIcon) || null;

  // ---------- 辅助函数 ----------
  function formatDate(dateStr) {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    const isToday = date.toDateString() === today.toDateString();
    const isYesterday = date.toDateString() === yesterday.toDateString();

    let prefix = '';
    if (isToday) prefix = '今天';
    else if (isYesterday) prefix = '昨天';

    return prefix ? `${prefix} · ${dateStr}` : dateStr;
  }

  function getSiteNames(siteIds, namesMap) {
    if (!siteIds || !namesMap) return [];
    return siteIds.map(id => namesMap[id] || `站点 ${id}`).filter(Boolean);
  }

  // ---------- 签到历史页面 ----------
  const HistoryPage = {
    name: 'SigninHistoryPage',
    setup() {
      const loading = ref(false);
      const historyData = ref({});

      async function fetchData() {
        if (!rc) return;
        loading.value = true;
        try {
          const res = await rc.get('/api/plugin-framework/plugins/autosignin/data/signin_history.json');
          historyData.value = res || {};
        } catch (e) {
          console.error('[AutoSignIn] 获取签到历史失败:', e);
        } finally {
          loading.value = false;
        }
      }

      onMounted(fetchData);

      const sortedDates = computed(() => {
        return Object.keys(historyData.value).sort((a, b) => b.localeCompare(a));
      });

      const summary = computed(() => {
        let totalSign = 0;
        let totalRetry = 0;
        for (const key of Object.keys(historyData.value)) {
          const d = historyData.value[key];
          totalSign += (d.sign || []).length;
          totalRetry += (d.retry || []).length;
        }
        return { totalDays: Object.keys(historyData.value).length, totalSign, totalRetry };
      });

      function renderStatCard(icon, label, value, colorVar) {
        return h('div', {
          style: {
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem',
            borderRadius: '0.75rem',
            border: '1px solid hsl(var(--border) / 0.5)',
            backgroundColor: 'hsl(var(--card))',
          }
        }, [
          IconifyIcon ? h(IconifyIcon, {
            icon,
            style: { fontSize: '1.5rem', color: `hsl(var(${colorVar}))` }
          }) : null,
          h('div', {}, [
            h('div', { style: { fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' } }, label),
            h('div', { style: { fontSize: '1.25rem', fontWeight: 700, color: 'hsl(var(--card-foreground))' } }, String(value)),
          ]),
        ]);
      }

      function renderTag(name, colorVar) {
        return h('span', {
          style: {
            display: 'inline-flex',
            alignItems: 'center',
            height: '1.75rem',
            fontSize: '0.8125rem',
            padding: '0 0.625rem',
            borderRadius: '0.375rem',
            backgroundColor: `hsl(var(${colorVar}) / 0.08)`,
            color: `hsl(var(${colorVar}))`,
            border: `1px solid hsl(var(${colorVar}) / 0.2)`,
            fontWeight: 500,
            whiteSpace: 'nowrap',
            lineHeight: 1,
          }
        }, name);
      }

      function renderDateCard(dateStr) {
        const dayData = historyData.value[dateStr];
        const namesMap = dayData.names || {};
        const signSites = getSiteNames(dayData.sign || [], namesMap);
        const retrySites = getSiteNames(dayData.retry || [], namesMap);

        return h('div', {
          style: {
            border: '1px solid hsl(var(--border) / 0.4)',
            borderRadius: '0.75rem',
            padding: '1.25rem',
            backgroundColor: 'hsl(var(--card))',
            marginBottom: '0.75rem',
          }
        }, [
          // 日期头部
          h('div', {
            style: {
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '1rem',
              paddingBottom: '0.75rem',
              borderBottom: '1px solid hsl(var(--border) / 0.25)',
            }
          }, [
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } }, [
              IconifyIcon ? h(IconifyIcon, {
                icon: 'lucide:calendar-days',
                style: { fontSize: '1rem', color: 'hsl(var(--primary))' }
              }) : null,
              h('span', { style: { fontWeight: 700, fontSize: '0.9375rem', color: 'hsl(var(--card-foreground))' } }, formatDate(dateStr)),
            ]),
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.75rem' } }, [
              h('span', { style: { display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'hsl(var(--success))' } }, [
                IconifyIcon ? h(IconifyIcon, { icon: 'lucide:check-circle-2', style: { fontSize: '0.875rem' } }) : null,
                String(signSites.length),
              ]),
              h('span', { style: { color: 'hsl(var(--border))' } }, '|'),
              h('span', { style: { display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'hsl(var(--warning))' } }, [
                IconifyIcon ? h(IconifyIcon, { icon: 'lucide:alert-circle', style: { fontSize: '0.875rem' } }) : null,
                String(retrySites.length),
              ]),
            ]),
          ]),

          // 已签到站点
          signSites.length > 0 ? h('div', { style: { marginBottom: '0.875rem' } }, [
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.375rem', marginBottom: '0.5rem' } }, [
              IconifyIcon ? h(IconifyIcon, {
                icon: 'lucide:check-circle-2',
                style: { fontSize: '0.875rem', color: 'hsl(var(--success))' }
              }) : null,
              h('span', { style: { fontSize: '0.75rem', color: 'hsl(var(--success))', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' } }, '已签到'),
            ]),
            h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '0.375rem' } },
              signSites.map(name => renderTag(name, 'success'))
            ),
          ]) : null,

          // 需重试站点
          retrySites.length > 0 ? h('div', {}, [
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.375rem', marginBottom: '0.5rem' } }, [
              IconifyIcon ? h(IconifyIcon, {
                icon: 'lucide:alert-triangle',
                style: { fontSize: '0.875rem', color: 'hsl(var(--warning))' }
              }) : null,
              h('span', { style: { fontSize: '0.75rem', color: 'hsl(var(--warning))', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' } }, '需重试'),
            ]),
            h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '0.375rem' } },
              retrySites.map(name => renderTag(name, 'warning'))
            ),
          ]) : null,
        ]);
      }

      return () => {
        // 页面头部
        const header = h('div', {
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1.25rem',
          }
        }, [
          h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } }, [
            IconifyIcon ? h(IconifyIcon, {
              icon: 'lucide:history',
              style: { fontSize: '1.25rem', color: 'hsl(var(--primary))' }
            }) : null,
            h('h2', { style: { fontSize: '1.125rem', fontWeight: 700, color: 'hsl(var(--foreground))' } }, '签到历史'),
          ]),
          h('button', {
            onClick: fetchData,
            style: {
              display: 'flex',
              alignItems: 'center',
              gap: '0.375rem',
              padding: '0.375rem 0.875rem',
              borderRadius: '0.5rem',
              border: '1px solid hsl(var(--border))',
              background: 'hsl(var(--background))',
              color: 'hsl(var(--foreground))',
              cursor: 'pointer',
              fontSize: '0.8125rem',
              fontWeight: 500,
            }
          }, [
            IconifyIcon ? h(IconifyIcon, { icon: 'lucide:refresh-cw', style: { fontSize: '0.875rem' } }) : null,
            '刷新',
          ]),
        ]);

        // 统计卡片
        const stats = h('div', {
          style: {
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: '0.75rem',
            marginBottom: '1.25rem',
          }
        }, [
          renderStatCard('lucide:calendar-days', '签到天数', summary.value.totalDays, 'primary'),
          renderStatCard('lucide:check-circle-2', '已签到', summary.value.totalSign, 'success'),
          renderStatCard('lucide:alert-triangle', '需重试', summary.value.totalRetry, 'warning'),
        ]);

        if (loading.value) {
          return h('div', { style: { padding: '1.5rem' } }, [
            header,
            stats,
            h('div', {
              style: {
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                padding: '4rem 1rem',
                color: 'hsl(var(--muted-foreground))',
                fontSize: '0.875rem',
              }
            }, [
              IconifyIcon ? h(IconifyIcon, { icon: 'lucide:loader-2', style: { fontSize: '1.25rem', animation: 'spin 1s linear infinite' } }) : null,
              '加载中...',
            ]),
          ]);
        }

        if (sortedDates.value.length === 0) {
          return h('div', { style: { padding: '1.5rem' } }, [
            header,
            h('div', {
              style: {
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '5rem 1rem',
                color: 'hsl(var(--muted-foreground))',
                textAlign: 'center',
              }
            }, [
              IconifyIcon ? h(IconifyIcon, {
                icon: 'lucide:calendar-x',
                style: { fontSize: '3rem', color: 'hsl(var(--muted-foreground) / 0.3)', marginBottom: '1rem' }
              }) : null,
              h('div', { style: { fontSize: '1rem', fontWeight: 600, marginBottom: '0.375rem', color: 'hsl(var(--foreground))' } }, '暂无签到记录'),
              h('div', { style: { fontSize: '0.8125rem' } }, '运行签到任务后，签到记录将显示在这里'),
            ]),
          ]);
        }

        return h('div', { style: { padding: '1.5rem' } }, [
          header,
          stats,
          ...sortedDates.value.map(renderDateCard),
        ]);
      };
    },
  };

  exports.HistoryPage = HistoryPage;
});
