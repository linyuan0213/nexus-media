/**
 * CookieCloud 插件前端 UMD 包（无需自定义 UI，复用框架默认配置表单）
 */
(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined'
    ? factory(exports, require('vue'))
    : typeof define === 'function' && define.amd
      ? define(['exports', 'vue'], factory)
      : (global = typeof globalThis !== 'undefined' ? globalThis : global || self,
         factory(global.__PLUGIN_cookiecloud__ = {}, global.Vue));
})(this, function (exports, Vue) {
  'use strict';
  exports.default = {};
});
