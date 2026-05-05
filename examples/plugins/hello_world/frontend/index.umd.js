/**
 * Hello World 插件前端 UMD 包
 * 暴露: HelloPage, SettingsPage, DashboardWidget
 */
(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined'
    ? factory(exports, require('vue'))
    : typeof define === 'function' && define.amd
      ? define(['exports', 'vue'], factory)
      : (global = typeof globalThis !== 'undefined' ? globalThis : global || self,
         factory(global.__PLUGIN_hello_world__ = {}, global.Vue));
})(this, function (exports, Vue) {
  'use strict';

  const { h, ref, computed, onMounted } = Vue;

  // ---------- DashboardWidget ----------
  const DashboardWidget = {
    name: 'HelloWorldDashboardWidget',
    setup() {
      const now = ref(new Date().toLocaleString());
      onMounted(() => {
        setInterval(() => { now.value = new Date().toLocaleString(); }, 1000);
      });
      return () =>
        h('div', {
          style: {
            padding: '16px',
            borderRadius: '8px',
            background: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            color: 'hsl(var(--card-foreground))',
          }
        }, [
          h('div', { style: { fontWeight: 600, marginBottom: '8px' } }, 'Hello World 插件'),
          h('div', { style: { fontSize: '0.875rem', color: 'hsl(var(--muted-foreground))' } },
            '当前时间：' + now.value),
          h('div', { style: { marginTop: '8px', fontSize: '0.75rem', color: 'hsl(var(--primary))' } },
            '这是插件注入到 Dashboard 的组件')
        ]);
    }
  };

  // ---------- HelloPage ----------
  const HelloPage = {
    name: 'HelloWorldPage',
    setup() {
      const count = ref(0);
      const greeting = ref('Hello from plugin!');

      onMounted(() => {
        try {
          // 尝试从插件上下文读取配置（如果页面是通过插件加载器渲染的，props 中会有 config）
          const propsConfig = (Vue.getCurrentInstance()?.props?.config) || {};
          if (propsConfig.greeting) greeting.value = propsConfig.greeting;
        } catch (e) { /* ignore */ }
      });

      return () =>
        h('div', { style: { padding: '24px' } }, [
          h('h1', {
            style: {
              fontSize: '1.5rem',
              fontWeight: 700,
              marginBottom: '16px',
              color: 'hsl(var(--foreground))'
            }
          }, greeting.value),
          h('p', { style: { color: 'hsl(var(--muted-foreground))', marginBottom: '16px' } },
            '这是 Hello World 示例插件注册的独立页面。'),
          h('button', {
            onClick: () => count.value++,
            style: {
              padding: '8px 16px',
              borderRadius: '6px',
              border: 'none',
              background: 'hsl(var(--primary))',
              color: 'hsl(var(--primary-foreground))',
              cursor: 'pointer',
            }
          }, `点击次数: ${count.value}`),
          h('div', { style: { marginTop: '24px', padding: '16px', borderRadius: '8px', background: 'hsl(var(--accent))' } },
            '插件页面可以完全自定义样式和行为。')
        ]);
    }
  };

  // ---------- SettingsPage ----------
  const SettingsPage = {
    name: 'HelloWorldSettings',
    props: ['config', 'onChange'],
    setup(props) {
      const local = ref({ ...props.config });

      const update = (key, value) => {
        local.value[key] = value;
        if (props.onChange) props.onChange(local.value);
      };

      return () =>
        h('div', { style: { padding: '16px' } }, [
          h('div', { style: { marginBottom: '16px' } }, [
            h('label', { style: { display: 'block', marginBottom: '4px', fontWeight: 500 } }, '问候语'),
            h('input', {
              value: local.value.greeting || '',
              onInput: (e) => update('greeting', e.target.value),
              style: {
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid hsl(var(--border))',
                background: 'hsl(var(--background))',
                color: 'hsl(var(--foreground))',
              }
            })
          ]),
          h('div', { style: { marginBottom: '16px' } }, [
            h('label', { style: { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' } }, [
              h('input', {
                type: 'checkbox',
                checked: local.value.show_timestamp,
                onChange: (e) => update('show_timestamp', e.target.checked),
              }),
              '显示时间戳'
            ])
          ]),
          h('div', { style: { marginBottom: '16px' } }, [
            h('label', { style: { display: 'block', marginBottom: '4px', fontWeight: 500 } }, '刷新间隔（秒）'),
            h('input', {
              type: 'number',
              value: local.value.refresh_interval || 60,
              onInput: (e) => update('refresh_interval', parseInt(e.target.value) || 0),
              style: {
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid hsl(var(--border))',
                background: 'hsl(var(--background))',
                color: 'hsl(var(--foreground))',
              }
            })
          ])
        ]);
    }
  };

  exports.HelloPage = HelloPage;
  exports.SettingsPage = SettingsPage;
  exports.DashboardWidget = DashboardWidget;
  exports.default = { HelloPage, SettingsPage, DashboardWidget };
});