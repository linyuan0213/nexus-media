/** DoubanSync 插件前端，包含 HistoryPage 历史记录页面 */

export default function(host) {
  const { h, ref, onMounted } = host.Vue;
  const IconifyIcon = host.IconifyIcon;
  const rc = host.api;

  // ---------- DoubanHistoryPage ----------
  const DoubanHistoryPage = {
    name: 'DoubanHistoryPage',
    setup() {
      const loading = ref(false);
      const records = ref([]);

      async function fetchData() {
        if (!rc) return;
        loading.value = true;
        try {
          const res = await rc.get('/plugin-framework/plugins/doubansync/data/history.json');
          records.value = res || [];
        } catch (e) {
          console.error('[DoubanSync] 获取历史记录失败:', e);
        } finally {
          loading.value = false;
        }
      }

      async function handleDelete(id) {
        if (!rc) return;
        try {
          await rc.delete(`/plugin-framework/plugins/doubansync/data/history.json/${id}`);
          fetchData();
        } catch (e) {
          console.error('[DoubanSync] 删除失败:', e);
        }
      }

      async function handleSync() {
        if (!rc) return;
        try {
          await rc.post('/plugin-framework/plugins/doubansync/run', {});
        } catch (e) {
          console.error('[DoubanSync] 同步失败:', e);
        }
      }

      function getStateTag(state) {
        const map = {
          DOWNLOADED: { label: '已下载', color: 'hsl(var(--success))' },
          RSS: { label: '已订阅', color: 'hsl(var(--primary))' },
          NEW: { label: '新增', color: 'hsl(var(--warning))' },
        };
        return map[state] || { label: '处理中', color: 'hsl(var(--muted-foreground))' };
      }

      onMounted(fetchData);

      return () => {
        const header = h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' } }, [
          h('h2', { style: { fontSize: '1.125rem', fontWeight: 600 } }, '豆瓣同步历史'),
          h('div', { style: { display: 'flex', gap: '0.5rem' } }, [
            h('button', { onClick: fetchData, style: { padding: '0.375rem 0.75rem', borderRadius: '0.375rem', border: '1px solid hsl(var(--border))', background: 'hsl(var(--background))', color: 'hsl(var(--foreground))', cursor: 'pointer', fontSize: '0.8125rem' } }, '刷新'),
            h('button', { onClick: handleSync, style: { padding: '0.375rem 0.75rem', borderRadius: '0.375rem', border: 'none', background: 'hsl(var(--primary))', color: 'hsl(var(--primary-foreground))', cursor: 'pointer', fontSize: '0.8125rem' } }, '立即同步'),
          ]),
        ]);

        if (loading.value) {
          return h('div', { style: { padding: '1rem' } }, [
            header,
            h('div', { style: { textAlign: 'center', padding: '2rem', color: 'hsl(var(--muted-foreground))' } }, '加载中...'),
          ]);
        }

        if (records.value.length === 0) {
          return h('div', { style: { padding: '1rem' } }, [
            header,
            h('div', { style: { textAlign: 'center', padding: '3rem 1rem', color: 'hsl(var(--muted-foreground))' } }, [
              IconifyIcon ? h(IconifyIcon, { icon: 'lucide:film', class: 'h-8 w-8 text-muted-foreground/40', width: 32, height: 32 }) : null,
              h('div', null, '暂无同步记录'),
            ]),
          ]);
        }

        const list = records.value.map((item) => {
          const tag = getStateTag(item.state);
          return h('div', { key: item.id, style: { display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid hsl(var(--border) / 0.6)', backgroundColor: 'hsl(var(--card))', marginBottom: '0.5rem' } }, [
            h('img', { src: item.image || '/static/img/no-image.png', style: { width: '3rem', height: '4rem', borderRadius: '0.25rem', objectFit: 'cover', flexShrink: 0 }, onError: (e) => { e.target.src = '/static/img/no-image.png'; } }),
            h('div', { style: { flex: 1, minWidth: 0 } }, [
              h('div', { style: { fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
                [item.name, item.year ? h('span', { style: { color: 'hsl(var(--muted-foreground))' } }, ` (${item.year})`) : null]
              ),
              h('div', { style: { fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.25rem' } },
                `${item.type} · ${item.rating ? '评分:' + item.rating + ' · ' : ''}${item.add_time || ''}`
              ),
            ]),
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } }, [
              h('span', { style: { fontSize: '0.6875rem', padding: '0.125rem 0.5rem', borderRadius: '9999px', backgroundColor: tag.color + '15', color: tag.color } }, tag.label),
              h('button', { onClick: () => { if (confirm(`确认删除 ${item.name}？`)) { handleDelete(item.id); } }, style: { padding: '0.25rem', border: 'none', background: 'transparent', color: 'hsl(var(--destructive))', cursor: 'pointer', fontSize: '0.875rem' } }, '🗑'),
            ]),
          ]);
        });

        return h('div', { style: { padding: '1rem' } }, [header, ...list]);
      };
    }
  };

  return { HistoryPage: DoubanHistoryPage };
}
