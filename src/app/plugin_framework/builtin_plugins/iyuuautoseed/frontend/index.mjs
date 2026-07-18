/** IYUU自动辅种 插件前端 */

export default function(host) {
  const { h, ref, reactive, onMounted } = host.Vue;
  const IconifyIcon = host.IconifyIcon;
  const rc = host.api;

  const API_BASE = '/plugin-framework/plugins/iyuuautoseed/api';

  const BindSitesPage = {
    name: 'BindSitesPage',
    setup() {
      const loading = ref(false);
      const sites = ref([]);
      const errorMsg = ref('');
      /** 每站点的输入与绑定结果: { [site]: { passkey, uid } } / { [site]: { ok, msg } } */
      const forms = reactive({});
      const results = reactive({});
      const binding = ref('');

      async function fetchData() {
        loading.value = true;
        errorMsg.value = '';
        try {
          const res = await rc.get(`${API_BASE}/bindable_sites`);
          sites.value = res || [];
          for (const s of sites.value) {
            if (!forms[s.site]) {
              forms[s.site] = { passkey: s.api_key || '', uid: s.bound_uid || '' };
            }
          }
        } catch (e) {
          console.error('[IYUUAutoSeed]', e);
          errorMsg.value = (e && e.message) || '获取站点列表失败';
          sites.value = [];
        } finally {
          loading.value = false;
        }
      }

      onMounted(fetchData);

      async function bind(row) {
        const form = forms[row.site] || {};
        if (!form.passkey || !form.uid) {
          results[row.site] = { ok: false, msg: `请填写 ${credentialLabel(row)} 和 uid` };
          return;
        }
        binding.value = row.site;
        try {
          await rc.post(`${API_BASE}/bind_site`, {
            site: row.site,
            passkey: form.passkey,
            uid: form.uid,
          });
          results[row.site] = { ok: true, msg: '绑定成功' };
        } catch (e) {
          results[row.site] = { ok: false, msg: (e && e.message) || '绑定失败' };
        } finally {
          binding.value = '';
        }
      }

      function credentialLabel(row) {
        // 凭证标签由站点定义的认证类型驱动（api_key → API Key，其余为 passkey）
        return row.auth_type === 'api_key' ? 'API Key' : 'passkey';
      }

      function renderIcon(icon, size, style) {
        return IconifyIcon
          ? h(IconifyIcon, { icon, style: { fontSize: size || '1rem', flexShrink: 0, ...style } })
          : null;
      }

      const inputStyle = {
        width: '100%',
        maxWidth: '220px',
        padding: '0.4375rem 0.75rem',
        borderRadius: '0.5rem',
        border: '1px solid hsl(var(--border))',
        background: 'hsl(var(--background))',
        color: 'hsl(var(--foreground))',
        fontSize: '0.8125rem',
        outline: 'none',
        transition: 'border-color 0.15s',
      };

      function renderBadge(text, kind) {
        const color = kind === 'success' ? 'success' : kind === 'error' ? 'destructive' : 'primary';
        return h('span', {
          style: {
            display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
            height: '1.5rem', padding: '0 0.5rem', borderRadius: '0.375rem',
            fontSize: '0.6875rem', fontWeight: 500, whiteSpace: 'nowrap',
            color: `hsl(var(--${color}))`,
            backgroundColor: `hsl(var(--${color}) / 0.08)`,
            border: `1px solid hsl(var(--${color}) / 0.2)`,
          },
        }, [
          kind === 'success' ? renderIcon('lucide:check-circle-2', '0.75rem') : null,
          kind === 'error' ? renderIcon('lucide:alert-circle', '0.75rem') : null,
          text,
        ]);
      }

      function renderRow(row, idx) {
        const form = forms[row.site] || {};
        const result = results[row.site];
        const isBinding = binding.value === row.site;

        const inputs = ['passkey', 'uid'].map(function(field) {
          return h('input', {
            key: row.site + field,
            style: inputStyle,
            type: field === 'passkey' ? 'password' : 'text',
            placeholder: field === 'passkey' ? credentialLabel(row) : 'uid',
            value: form[field] || '',
            onInput: function(e) { form[field] = e.target.value; },
          });
        });

        return h('div', {
          key: row.site,
          style: {
            display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem 1rem',
            padding: '0.75rem 1rem',
            backgroundColor: idx % 2 === 1 ? 'hsl(var(--accent) / 0.15)' : 'transparent',
            borderTop: idx === 0 ? 'none' : '1px solid hsl(var(--border) / 0.3)',
          },
        }, [
          // 站点信息
          h('div', {
            style: { display: 'flex', flexDirection: 'column', gap: '0.25rem', flex: '1 1 200px', minWidth: 0 },
          }, [
            h('div', {
              style: { display: 'flex', alignItems: 'center', gap: '0.625rem' },
            }, [
              h('span', {
                style: {
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '2rem', height: '2rem', borderRadius: '0.5rem', flexShrink: 0,
                  backgroundColor: 'hsl(var(--primary) / 0.1)', color: 'hsl(var(--primary))',
                },
              }, [renderIcon('lucide:globe', '1rem')]),
              h('div', { style: { minWidth: 0 } }, [
                h('div', {
                  style: { fontSize: '0.875rem', fontWeight: 600, color: 'hsl(var(--foreground))', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
                }, row.nickname || row.site),
                h('div', {
                  style: { fontSize: '0.6875rem', color: 'hsl(var(--muted-foreground))', fontFamily: 'monospace' },
                }, row.site),
              ]),
            ]),
            h('div', {
              style: { display: 'flex', flexWrap: 'wrap', gap: '0.25rem' },
            }, [
              row.local ? renderBadge('本地已配置', 'primary') : null,
              row.bound ? renderBadge(`已绑定${row.bound_time ? ' · ' + row.bound_time.slice(0, 10) : ''}`, 'success') : null,
            ]),
          ]),
          // 凭证输入
          h('div', {
            style: { display: 'flex', flex: '1 1 320px', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' },
          }, inputs),
          // 操作区
          h('div', {
            style: { display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: 'auto' },
          }, [
            result ? renderBadge(result.msg, result.ok ? 'success' : 'error') : null,
            h('button', {
              style: {
                display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                height: '2rem', padding: '0 0.875rem',
                borderRadius: '0.5rem', border: 'none',
                background: 'hsl(var(--primary))', color: 'hsl(var(--primary-foreground))',
                cursor: isBinding ? 'not-allowed' : 'pointer',
                fontSize: '0.8125rem', fontWeight: 500, whiteSpace: 'nowrap',
                opacity: isBinding ? 0.6 : 1,
                transition: 'opacity 0.15s',
              },
              disabled: isBinding,
              onClick: function() { bind(row); },
            }, [
              renderIcon(isBinding ? 'lucide:loader-2' : 'lucide:link', '0.875rem'),
              isBinding ? '绑定中' : '绑定',
            ]),
          ]),
        ]);
      }

      return function() {
        const header = h('div', {
          style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' },
        }, [
          h('div', {}, [
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } }, [
              renderIcon('lucide:link', '1.25rem', { color: 'hsl(var(--primary))' }),
              h('h2', { style: { fontSize: '1.125rem', fontWeight: 700, color: 'hsl(var(--foreground))' } }, '绑定站点'),
            ]),
            h('p', {
              style: { marginTop: '0.25rem', fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' },
            }, '将站点凭证绑定到 IYUU 账号，可提高鉴权站点的辅种匹配质量'),
          ]),
          h('button', {
            onClick: fetchData,
            style: {
              display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
              height: '2rem', padding: '0 0.875rem',
              borderRadius: '0.5rem', border: '1px solid hsl(var(--border))',
              background: 'hsl(var(--card))', color: 'hsl(var(--foreground))',
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

        if (sites.value.length === 0) {
          return h('div', { style: { padding: '1.5rem' } }, [
            header,
            h('div', {
              style: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '5rem 1rem', borderRadius: '0.75rem', border: '1px dashed hsl(var(--border) / 0.5)', backgroundColor: 'hsl(var(--card))' },
            }, [
              renderIcon('lucide:unlink', '2.5rem', { color: 'hsl(var(--muted-foreground))' }),
              h('p', { style: { marginTop: '0.75rem', fontSize: '0.9375rem', fontWeight: 600, color: 'hsl(var(--foreground))' } }, '暂无可绑定站点'),
              h('p', { style: { marginTop: '0.25rem', fontSize: '0.75rem', color: errorMsg.value ? 'hsl(var(--destructive))' : 'hsl(var(--muted-foreground))' } },
                errorMsg.value || '请先在插件配置中填写 IYUU Token'),
            ]),
          ]);
        }

        return h('div', { style: { padding: '1.5rem' } }, [
          header,
          h('div', {
            style: {
              borderRadius: '0.75rem', border: '1px solid hsl(var(--border) / 0.4)',
              overflow: 'hidden', backgroundColor: 'hsl(var(--card))',
            },
          }, [
            h('div', {
              style: {
                display: 'flex', alignItems: 'center', gap: '0.375rem',
                padding: '0.625rem 1rem', fontSize: '0.6875rem', fontWeight: 700,
                color: 'hsl(var(--muted-foreground))', backgroundColor: 'hsl(var(--accent) / 0.3)',
                textTransform: 'uppercase', letterSpacing: '0.05em',
              },
            }, [
              renderIcon('lucide:shield-check', '0.875rem'),
              `支持鉴权的站点（${sites.value.length}）`,
            ]),
            ...sites.value.map(renderRow),
          ]),
        ]);
      };
    },
  };

  return { BindSitesPage };
}
