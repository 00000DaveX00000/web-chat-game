/**
 * WebSocket client for the AI Raid Battle game.
 * Provides connection management, auto-reconnect, and event dispatch.
 */
var GameWS = (function () {
  'use strict';

  var _ws = null;
  var _listeners = {};
  var _reconnectTimer = null;
  var _reconnectDelay = 1000;
  var _maxReconnectDelay = 8000;
  var _connected = false;

  function _getUrl() {
    var loc = window.location;
    var proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    return proto + '//' + loc.host + '/ws';
  }

  function _updateStatus(connected) {
    _connected = connected;
    var el = document.getElementById('ws-status');
    if (el) {
      el.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
      el.className = connected ? 'connected' : '';
    }
  }

  function connect() {
    if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    var url = _getUrl();
    _ws = new WebSocket(url);

    _ws.onopen = function () {
      _reconnectDelay = 1000;
      _updateStatus(true);
      _emit('open', null);
      _addLog('System connected.', 'system');
    };

    _ws.onmessage = function (evt) {
      var msg;
      try {
        msg = JSON.parse(evt.data);
      } catch (e) {
        return;
      }
      var type = msg.type;
      if (type === 'state_update') {
        _emit('state_update', msg.data);
      } else if (type === 'combat_log') {
        _emit('combat_log', msg.data);
        if (msg.data) {
          var logText = msg.data.text || msg.data.message || JSON.stringify(msg.data);
          var logType = msg.data.log_type || msg.data.type || 'system';
          _addLog(logText, logType);
        }
      } else if (type === 'game_over') {
        _emit('game_over', msg.data);
      } else if (type === 'animation') {
        _emit('animation', msg.data);
      }
    };

    _ws.onclose = function () {
      _updateStatus(false);
      _emit('close', null);
      _scheduleReconnect();
    };

    _ws.onerror = function () {
      _updateStatus(false);
    };
  }

  function _scheduleReconnect() {
    if (_reconnectTimer) return;
    _reconnectTimer = setTimeout(function () {
      _reconnectTimer = null;
      connect();
      _reconnectDelay = Math.min(_reconnectDelay * 2, _maxReconnectDelay);
    }, _reconnectDelay);
  }

  function send(obj) {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify(obj));
    }
  }

  function sendGodCommand(text) {
    send({ type: 'god_command', content: text });
    _addLog('[GOD] ' + text, 'phase');
  }

  /* ---- Event system ---- */
  function on(eventType, callback) {
    if (!_listeners[eventType]) _listeners[eventType] = [];
    _listeners[eventType].push(callback);
  }

  function off(eventType, callback) {
    var arr = _listeners[eventType];
    if (!arr) return;
    var idx = arr.indexOf(callback);
    if (idx !== -1) arr.splice(idx, 1);
  }

  function _emit(eventType, data) {
    var arr = _listeners[eventType];
    if (!arr) return;
    for (var i = 0; i < arr.length; i++) {
      arr[i](data);
    }
  }

  /* ---- Battle log DOM helper ---- */
  function _addLog(text, logType) {
    var container = document.getElementById('battle-log');
    if (!container) return;
    var div = document.createElement('div');
    div.className = 'log-entry ' + (logType || 'system');
    div.textContent = text;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  /* ---- God command UI binding ---- */
  function _initUI() {
    var input = document.getElementById('god-input');
    var btn = document.getElementById('god-send');
    if (!input || !btn) return;

    function submitCmd() {
      var text = input.value.trim();
      if (!text) return;
      sendGodCommand(text);
      input.value = '';
    }

    btn.addEventListener('click', submitCmd);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') submitCmd();
    });
  }

  /* Initialize when DOM is ready */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initUI);
  } else {
    _initUI();
  }

  return {
    connect: connect,
    send: send,
    sendGodCommand: sendGodCommand,
    on: on,
    off: off,
    isConnected: function () { return _connected; }
  };
})();
