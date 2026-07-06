/** CookieCloud 插件前端 */

export default function(host) {
  const { h, ref, onMounted } = host.Vue;
  const IconifyIcon = host.IconifyIcon;
  const rc = host.api;

  const SyncHistoryPage = {
    name: 'SyncHistoryPage',
    setup() {
      const loading = ref(false);
      const records = ref([]);

      async function fetchData() {
        loading.value = true;
        try {
          const res = await rc.get('/plugin-framework/plugins/cookiecloud/data/sync_history.json');
          records.value = res || [];
        } catch (e) {
          console.error('[CookieCloud]', e);
        } finally {
          loading.value = false;
        }
      }

      onMounted(fetchData);

      function renderIcon(icon, size) {
        return IconifyIcon ? h(IconifyIcon, { icon, style: { fontSize: size || '1rem' } }) : null;
      }

      function renderStatusBadge(status) {
        var color = status === '成功' ? 'success' : status === '失败' ? 'destructive' : 'warning';
        return h('span', {
          style: {
            display: 'inline-flex', alignItems: 'center', height: '1.75rem',
            padding: '0 0.625rem', borderRadius: '0.375rem', fontSize: '0.75rem',
            fontWeight: 500, color: `hsl(var(--${color}))`,
            backgroundColor: `hsl(var(--${color}) / 0.08)`,
            border: `1px solid hsl(var(--${color}) / 0.2)`,
          },
        }, status);
      }

      function renderActionBadge(action) {
        return h('span', {
          style: {
            display: 'inline-flex', alignItems: 'center', height: '1.75rem',
            padding: '0 0.625rem', borderRadius: '0.375rem', fontSize: '0.75rem',
            fontWeight: 500, color: 'hsl(var(--primary))',
            backgroundColor: 'hsl(var(--primary) / 0.08)',
            border: '1px solid hsl(var(--primary) / 0.2)',
          },
        }, action);
      }

      return () => {
        var header = h('div', {
          style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' },
        }, [
          h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } }, [
            renderIcon('lucide:history', '1.25rem'),
            h('h2', { style: { fontSize: '1.125rem', fontWeight: 700, color: 'hsl(var(--foreground))' } }, '同步记录'),
          ]),
          h('button', {
            onClick: fetchData,
            style: {
              display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.375rem 0.875rem',
              borderRadius: '0.5rem', border: '1px solid hsl(var(--border))',
              background: 'hsl(var(--accent))', color: 'hsl(var(--accent-foreground))',
              cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 500,
            },
          }, [renderIcon('lucide:refresh-cw', '0.875rem'), '刷新']),
        ]);

        if (loading.value) {
          return h('div', { style: { padding: '1.5rem' } }, [
            header,
            h('div', {
              style: { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '4rem', color: 'hsl(var(--muted-foreground))', gap: '0.5rem' },
            }, [renderIcon('lucide:loader-2', '1.25rem'), '加载中...']),
          ]);
        }

        if (records.value.length === 0) {
          return h('div', { style: { padding: '1.5rem' } }, [
            header,
            h('div', {
              style: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '5rem 1rem', borderRadius: '0.75rem', border: '1px dashed hsl(var(--border) / 0.5)', backgroundColor: 'hsl(var(--card))' },
            }, [
              renderIcon('lucide:cloud-off', '2.5rem'),
              h('p', { style: { marginTop: '0.75rem', fontSize: '0.9375rem', fontWeight: 600, color: 'hsl(var(--foreground))' } }, '暂无同步记录'),
              h('p', { style: { marginTop: '0.25rem', fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' } }, '配置 CookieCloud 服务器后，运行一次同步即可查看结果'),
            ]),
          ]);
        }

        return h('div', { style: { padding: '1.5rem' } }, [
          header,
          ...records.value.map(function(r, idx) {
            var stats = h('div', {
              style: { display: 'flex', gap: '1rem', marginBottom: '1rem', padding: '0.75rem 1rem', borderRadius: '0.75rem', border: '1px solid hsl(var(--border) / 0.4)', backgroundColor: 'hsl(var(--card))' },
            }, [
              h('div', {}, [h('span', { style: { fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' } }, r.time)]),
              h('div', { style: { display: 'flex', gap: '1rem', marginLeft: 'auto' } }, [
                h('span', { style: { fontSize: '0.75rem', color: 'hsl(var(--success))' } }, '更新 ' + r.update_ok),
                h('span', { style: { fontSize: '0.75rem', color: 'hsl(var(--primary))' } }, '新增 ' + r.add_ok),
                h('span', { style: { fontSize: '0.75rem', color: 'hsl(var(--destructive))' } }, '失败 ' + r.failed),
              ]),
            ]);

            var thStyle = { padding: '0.5rem 0.75rem', fontSize: '0.6875rem', fontWeight: 700, color: 'hsl(var(--muted-foreground))', textAlign: 'left', borderBottom: '1px solid hsl(var(--border) / 0.4)', textTransform: 'uppercase', letterSpacing: '0.05em' };
            var tdStyle = { padding: '0.5rem 0.75rem', fontSize: '0.75rem', color: 'hsl(var(--card-foreground))', borderBottom: '1px solid hsl(var(--border) / 0.15)' };

            var table = h('div', {
              style: { borderRadius: '0.75rem', border: '1px solid hsl(var(--border) / 0.4)', overflow: 'hidden', backgroundColor: 'hsl(var(--card))' },
            }, [
              h('div', {
                style: { display: 'grid', gridTemplateColumns: 'minmax(80px, auto) 1fr 150px 80px', backgroundColor: 'hsl(var(--accent) / 0.3)' },
              }, [
                h('div', { style: thStyle }, '操作'),
                h('div', { style: thStyle }, '站点'),
                h('div', { style: thStyle }, '域名'),
                h('div', { style: { ...thStyle, textAlign: 'center' } }, '状态'),
              ]),
              ...(r.results || []).map(function(item) {
                return h('div', {
                  key: item.domain + idx,
                  style: { display: 'grid', gridTemplateColumns: 'minmax(80px, auto) 1fr 150px 80px', alignItems: 'center' },
                }, [
                  h('div', { style: tdStyle }, renderActionBadge(item.action)),
                  h('div', { style: tdStyle }, [
                    h('span', { style: { fontWeight: 500 } }, item.site || item.domain),
                    item.reason ? h('span', { style: { marginLeft: '0.5rem', fontSize: '0.6875rem', color: 'hsl(var(--muted-foreground))' } }, item.reason) : null,
                  ]),
                  h('div', { style: { ...tdStyle, fontFamily: 'monospace', fontSize: '0.6875rem', color: 'hsl(var(--muted-foreground))' } }, item.domain),
                  h('div', { style: { ...tdStyle, textAlign: 'center' } }, renderStatusBadge(item.status)),
                ]);
              }),
            ]);

            return h('div', { key: r.time, style: { marginBottom: '1.25rem' } }, [stats, table]);
          }),
        ]);
      };
    },
  };

  return { SyncHistoryPage };
}
