/**
 * WebSocket client for the AI Raid Battle game.
 * Handles connection, state updates, battle log, character cards,
 * boss info panel, game timer, command bar, and tab filtering.
 */
var GameWS = (function () {
  'use strict';

  var _ws = null;
  var _listeners = {};
  var _reconnectTimer = null;
  var _reconnectDelay = 1000;
  var _maxReconnectDelay = 8000;
  var _connected = false;
  var _gameRunning = false;
  var _activeLogFilter = 'all';

  // Role display config
  var ROLE_ICONS = {
    tank: '\u{1F6E1}',   // shield
    healer: '\u{2695}',  // medical
    mage: '\u{1F52E}',   // crystal ball
    rogue: '\u{1F5E1}',  // dagger
    hunter: '\u{1F3F9}'  // bow
  };

  var ROLE_NAMES = {
    tank: '\u5766\u514B',     // 坦克
    healer: '\u6CBB\u7597',   // 治疗
    mage: '\u6CD5\u5E08',     // 法师
    rogue: '\u76D7\u8D3C',    // 盗贼
    hunter: '\u730E\u4EBA'    // 猎人
  };

  function _getUrl() {
    var loc = window.location;
    var proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    return proto + '//' + loc.host + '/ws';
  }

  /* ---- Connection status ---- */
  function _updateStatus(connected) {
    _connected = connected;
    var el = document.getElementById('ws-status');
    if (el) {
      el.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
      el.className = connected ? 'connected' : '';
    }
  }

  /* ---- Game status ---- */
  function _updateGameStatus(running, result) {
    _gameRunning = running;
    var badge = document.getElementById('game-status-badge');
    var startBtn = document.getElementById('btn-start');
    var stopBtn = document.getElementById('btn-stop');

    if (badge) {
      if (result && result !== 'stopped') {
        badge.textContent = result === 'victory' ? 'VICTORY!' : 'DEFEAT';
        badge.className = result === 'victory' ? 'victory' : 'defeat';
      } else if (running) {
        badge.textContent = 'FIGHTING';
        badge.className = 'fighting';
      } else {
        badge.textContent = 'WAITING';
        badge.className = '';
      }
    }

    if (startBtn) startBtn.disabled = running;
    if (stopBtn) stopBtn.disabled = !running;
  }

  /* ---- Timer ---- */
  function _updateTimer(gameTime) {
    var el = document.getElementById('game-timer');
    if (!el) return;
    var totalSec = Math.floor(gameTime || 0);
    var min = Math.floor(totalSec / 60);
    var sec = totalSec % 60;
    el.textContent = (min < 10 ? '0' : '') + min + ':' + (sec < 10 ? '0' : '') + sec;
  }

  /* ---- Phase badge ---- */
  function _updatePhaseBadge(phase) {
    var el = document.getElementById('phase-badge');
    if (!el) return;
    var names = { 1: 'P1 \u89C9\u9192', 2: 'P2 \u72C2\u6012', 3: 'P3 \u706D\u4E16' };
    el.textContent = names[phase] || 'P' + phase;
    el.className = phase >= 3 ? 'p3' : phase >= 2 ? 'p2' : '';
  }

  /* ---- Header boss HP ---- */
  function _updateHeaderBossHp(boss) {
    var fill = document.getElementById('header-boss-hp-fill');
    var text = document.getElementById('header-boss-hp-text');
    if (!fill || !text || !boss) return;
    var pct = boss.hp_percent !== undefined ? boss.hp_percent : (boss.hp / boss.max_hp * 100);
    fill.style.width = Math.max(0, Math.min(100, pct)) + '%';
    text.textContent = Math.round(pct) + '%';
  }

  /* ---- Boss Info Panel ---- */
  function _updateBossInfo(boss) {
    if (!boss) return;

    var nameEl = document.getElementById('boss-info-name');
    var fillEl = document.getElementById('boss-hp-bar-fill');
    var hpTextEl = document.getElementById('boss-hp-text');
    var phaseEl = document.getElementById('boss-phase-text');
    var castBar = document.getElementById('boss-cast-bar');
    var castName = document.getElementById('boss-cast-name');
    var castFill = document.getElementById('boss-cast-fill');
    var castTime = document.getElementById('boss-cast-time');
    var mechEl = document.getElementById('boss-mechanics');
    var debuffEl = document.getElementById('boss-debuffs');
    var enrageEl = document.getElementById('boss-enrage');

    if (nameEl) nameEl.textContent = boss.name || 'BOSS';

    var pct = boss.hp_percent !== undefined ? boss.hp_percent : (boss.hp / boss.max_hp * 100);
    if (fillEl) fillEl.style.width = Math.max(0, Math.min(100, pct)) + '%';
    if (hpTextEl) hpTextEl.textContent = Math.round(pct * 10) / 10 + '% (' + boss.hp + '/' + boss.max_hp + ')';

    var phaseNames = { 1: 'Phase 1 - \u89C9\u9192', 2: 'Phase 2 - \u72C2\u6012', 3: 'Phase 3 - \u706D\u4E16' };
    if (phaseEl) phaseEl.textContent = phaseNames[boss.phase] || 'Phase ' + boss.phase;

    // Cast bar
    if (castBar) {
      if (boss.casting) {
        castBar.classList.remove('hidden');
        if (castName) castName.textContent = boss.casting.name;
        if (castTime) castTime.textContent = boss.casting.remaining.toFixed(1) + 's';
        var totalCast = boss.casting.name === '\u706D\u4E16\u4E4B\u708E' ? 3.0 : 2.0;
        var progress = Math.max(0, 1 - boss.casting.remaining / totalCast) * 100;
        if (castFill) castFill.style.width = progress + '%';
      } else {
        castBar.classList.add('hidden');
      }
    }

    // Mechanics (fissures + traps + adds)
    if (mechEl) {
      var mechHtml = '';
      var fissures = boss.fissures || [];
      for (var i = 0; i < fissures.length; i++) {
        mechHtml += '<div class="mech-item">\u7194\u5CA9\u88C2\u96D9 \u2192 ' + (ROLE_NAMES[fissures[i].target] || fissures[i].target) + ' (' + fissures[i].duration.toFixed(1) + 's)</div>';
      }
      var traps = boss.traps || [];
      for (var j = 0; j < traps.length; j++) {
        mechHtml += '<div class="mech-item">\u7194\u5CA9\u9677\u9631 \u2192 ' + (ROLE_NAMES[traps[j].target] || traps[j].target) + ' (' + traps[j].countdown.toFixed(1) + 's)</div>';
      }
      var adds = boss.adds || [];
      var aliveAdds = 0;
      for (var k = 0; k < adds.length; k++) {
        if (adds[k].alive) aliveAdds++;
      }
      if (aliveAdds > 0) {
        mechHtml += '<div class="mech-item">\u7194\u5CA9\u5143\u7D20 \u00D7' + aliveAdds + ' \u5B58\u6D3B</div>';
      }
      mechEl.innerHTML = mechHtml;
    }

    // Debuffs on boss
    if (debuffEl) {
      var dHtml = '';
      var debuffs = boss.debuffs || [];
      for (var d = 0; d < debuffs.length; d++) {
        dHtml += debuffs[d].name + '(' + debuffs[d].duration.toFixed(1) + 's) ';
      }
      debuffEl.textContent = dHtml ? 'Debuff: ' + dHtml : '';
    }

    // Enrage
    if (enrageEl) {
      if (boss.enraged) {
        enrageEl.classList.remove('hidden');
        enrageEl.textContent = '\u72C2\u66B4\u4E2D!';
      } else if (boss.enrage_timer !== null && boss.enrage_timer !== undefined) {
        enrageEl.classList.remove('hidden');
        enrageEl.textContent = '\u72C2\u66B4\u5012\u8BA1: ' + Math.ceil(boss.enrage_timer) + 's';
      } else {
        enrageEl.classList.add('hidden');
      }
    }
  }

  /* ---- Character Cards ---- */
  function _updateCharCards(characters) {
    if (!characters) return;
    var roles = ['tank', 'healer', 'mage', 'rogue', 'hunter'];
    for (var i = 0; i < roles.length; i++) {
      var role = roles[i];
      var c = characters[role];
      if (!c) continue;
      _updateOneCard(role, c);
    }
  }

  function _updateOneCard(role, c) {
    var card = document.getElementById('card-' + role);
    if (!card) return;

    var alive = c.alive !== false && c.hp > 0;

    // Dead state
    if (alive) {
      card.classList.remove('dead');
    } else {
      card.classList.add('dead');
    }

    // Header
    var iconEl = card.querySelector('.card-icon');
    var nameEl = card.querySelector('.card-name');

    if (iconEl) iconEl.textContent = ROLE_ICONS[role] || '';
    if (nameEl) nameEl.textContent = (ROLE_NAMES[role] || role);

    // Source tag (decision source)
    _updateSourceTag(card, c);

    // HP bar
    var hpPct = c.max_hp > 0 ? (c.hp / c.max_hp) : 0;
    var hpFill = card.querySelector('.hp-fill');
    var hpText = card.querySelector('.hp-text');
    if (hpFill) {
      hpFill.style.width = (hpPct * 100) + '%';
      hpFill.className = 'bar-fill hp-fill' + (hpPct > 0.6 ? '' : hpPct > 0.3 ? ' mid' : ' low');
    }
    if (hpText) hpText.textContent = 'HP ' + c.hp + '/' + c.max_hp;

    // MP bar
    var mpPct = c.max_mana > 0 ? (c.mana / c.max_mana) : 0;
    var mpFill = card.querySelector('.mp-fill');
    var mpText = card.querySelector('.mp-text');
    if (mpFill) mpFill.style.width = (mpPct * 100) + '%';
    if (mpText) mpText.textContent = (c.resource_name || 'MP') + ' ' + c.mana + '/' + c.max_mana;

    // Skill slots (WoW-style)
    _updateSkillSlots(card, c);

    // Cast bar
    var castBarEl = card.querySelector('.card-cast-bar');
    if (castBarEl) {
      if (c.casting) {
        castBarEl.classList.remove('hidden');
        var castFillEl = castBarEl.querySelector('.card-cast-fill');
        var castTextEl = castBarEl.querySelector('.card-cast-text');
        if (castFillEl) castFillEl.style.width = '50%';
        if (castTextEl) castTextEl.textContent = c.casting.skill_name + ' ' + c.casting.remaining.toFixed(1) + 's';
      } else {
        castBarEl.classList.add('hidden');
      }
    }

    // Instruction (what god command / environment instruction was active)
    var instrEl = card.querySelector('.card-instruction');
    if (instrEl) {
      var instrText = '';
      if (c.last_action && c.last_action.instruction) {
        instrText = c.last_action.instruction;
      }
      if (instrText) {
        instrEl.textContent = '\u{1F4E5} \u6307\u4EE4: "' + instrText + '"';
        instrEl.style.display = '';
      } else {
        instrEl.textContent = '';
        instrEl.style.display = 'none';
      }
    }

    // Action (what the agent actually did)
    var actionEl = card.querySelector('.card-action');
    if (actionEl) {
      if (c.last_action && c.last_action.skill_name) {
        var actionTarget = c.last_action.target || '';
        var actionSource = c.last_action.source || '';
        var sourceIcon = actionSource === 'ai' ? '\u{1F916}' : actionSource === 'timeout' ? '\u23F1' : '\u2699';
        actionEl.textContent = sourceIcon + ' ' + c.last_action.skill_name + ' \u2192 ' + actionTarget;
        actionEl.className = 'card-action source-' + actionSource;
      } else {
        actionEl.textContent = '';
        actionEl.className = 'card-action';
      }
    }

    // Reason (AI decision reasoning)
    var reasonEl = card.querySelector('.card-reason');
    if (reasonEl) {
      if (c.last_action && c.last_action.reason) {
        reasonEl.textContent = '\u{1F4AD} "' + c.last_action.reason + '"';
      } else {
        reasonEl.textContent = '';
      }
    }

    // Buffs + Debuffs
    var buffsEl = card.querySelector('.card-buffs');
    if (buffsEl) {
      var bhtml = '';
      var buffs = c.buffs || [];
      for (var b = 0; b < buffs.length; b++) {
        bhtml += '<span class="buff-item">' + buffs[b].name + '(' + Math.ceil(buffs[b].duration) + 's) </span>';
      }
      var debuffs = c.debuffs || [];
      for (var d = 0; d < debuffs.length; d++) {
        bhtml += '<span class="debuff-item">' + debuffs[d].name + '(' + Math.ceil(debuffs[d].duration) + 's) </span>';
      }
      buffsEl.innerHTML = bhtml || '';
    }
  }

  /* ---- Source Tag (Decision Source) ---- */
  function _updateSourceTag(card, charData) {
    var tag = card.querySelector('.source-tag');
    if (!tag) return;
    var la = charData.last_action;
    var alive = charData.alive !== false && charData.hp > 0;

    if (!alive) {
      tag.textContent = '\u2620 \u5DF2\u9635\u4EA1';
      tag.className = 'source-tag dead';
    } else if (la && la.source === 'ai') {
      tag.textContent = '\u{1F916} AI\u51B3\u7B56';
      tag.className = 'source-tag ai-decision';
    } else if (la && la.source === 'timeout') {
      tag.textContent = '\u23F1 \u8D85\u65F6\u9ED8\u8BA4';
      tag.className = 'source-tag timeout';
    } else if (la && la.source === 'auto') {
      tag.textContent = '\u2699 \u81EA\u52A8\u56DE\u9000';
      tag.className = 'source-tag auto';
    } else {
      tag.textContent = '\u23F3 \u7B49\u5F85\u4E2D';
      tag.className = 'source-tag waiting';
    }
  }

  /* ---- Skill Slots (WoW-style) ---- */
  function _updateSkillSlots(card, charData) {
    var skills = charData.skills || [];
    var cooldowns = charData.cooldowns || {};
    var lastAction = charData.last_action;
    var slots = card.querySelectorAll('.skill-slot');
    var now = Date.now() / 1000;

    for (var i = 0; i < Math.min(skills.length, 4); i++) {
      var skill = skills[i];
      var slot = slots[i];
      if (!slot) continue;

      var cd = cooldowns[String(skill.id)] || 0;
      var isActive = lastAction && lastAction.source === 'ai'
        && lastAction.skill_name === skill.name
        && (now - lastAction.time) < 2;

      // Reset classes
      slot.className = 'skill-slot';

      // Skill icon (name)
      var iconEl = slot.querySelector('.skill-icon');
      var cdTextEl = slot.querySelector('.cd-text');

      if (iconEl) iconEl.textContent = skill.name;

      if (isActive) {
        slot.classList.add('active-tool-call');
        if (cdTextEl) cdTextEl.textContent = '\u2605AI';
      } else if (cd > 0) {
        slot.classList.add('on-cooldown');
        if (cdTextEl) cdTextEl.textContent = Math.ceil(cd) + 's';
      } else {
        slot.classList.add('ready');
        if (cdTextEl) cdTextEl.textContent = 'RDY';
      }

      // Tooltip on hover
      slot.title = skill.name + (cd > 0 ? ' (CD: ' + Math.ceil(cd) + 's)' : ' (Ready)');
    }
  }

  /* ---- Log classification (improved) ---- */
  function _classifyLog(text) {
    if (!text) return 'system';
    // AI decision / timeout
    if (text.indexOf('\u{1F916}') !== -1 || text.indexOf('\u8C03\u7528') !== -1) {
      return 'ai_decision';
    }
    if (text.indexOf('\u23F1') !== -1 && text.indexOf('\u8D85\u65F6') !== -1) {
      return 'ai_decision';
    }
    // Command / God
    if (text.indexOf('[God]') !== -1 || text.indexOf('[DM]') !== -1 || text.indexOf('\u4E0A\u5E1D\u6307\u4EE4') !== -1) {
      return 'cmd';
    }
    // Mechanic / Phase
    if (text.indexOf('Phase') !== -1 || text.indexOf('===') !== -1 || text.indexOf('>>>') !== -1 ||
        text.indexOf('\u72C2\u66B4') !== -1 || text.indexOf('\u706D\u4E16') !== -1 || text.indexOf('\u70C8\u7130\u98CE\u66B4') !== -1 ||
        text.indexOf('\u53EC\u5524') !== -1 || text.indexOf('\u9677\u9631') !== -1 || text.indexOf('\u88C2\u96D9') !== -1 ||
        text.indexOf('\u8BFB\u6761') !== -1 || text.indexOf('\u6253\u65AD') !== -1) {
      return 'mech';
    }
    // Heal
    if (text.indexOf('\u6CBB\u7597') !== -1 || text.indexOf('\u6062\u590D') !== -1 || text.indexOf('\u590D\u6D3B') !== -1) {
      return 'heal';
    }
    // Damage
    if (text.indexOf('\u4F24\u5BB3') !== -1 || text.indexOf('\u547D\u4E2D') !== -1 || text.indexOf('\u706C\u70E7') !== -1 ||
        text.indexOf('\u653B\u51FB') !== -1 || text.indexOf('\u7206\u70B8') !== -1 || text.indexOf('\u9635\u4EA1') !== -1 ||
        text.indexOf('\u4F7F\u7528') !== -1) {
      return 'damage';
    }
    return 'system';
  }

  /* ---- Battle log with time prefix ---- */
  var _logCount = 0;
  var _MAX_LOGS = 300;
  var _logEntries = [];

  function _formatTime(gameTime) {
    var totalSec = Math.floor(gameTime || 0);
    var min = Math.floor(totalSec / 60);
    var sec = totalSec % 60;
    return (min < 10 ? '0' : '') + min + ':' + (sec < 10 ? '0' : '') + sec;
  }

  function _addLog(text, logType, gameTime) {
    var container = document.getElementById('battle-log');
    if (!container) return;

    var timeStr = _formatTime(gameTime);
    var entry = { text: text, type: logType || 'system', time: timeStr };
    _logEntries.push(entry);

    while (_logEntries.length > _MAX_LOGS) {
      _logEntries.shift();
    }

    if (_activeLogFilter === 'all' || _activeLogFilter === entry.type) {
      var div = document.createElement('div');
      div.className = 'log-entry ' + entry.type;
      div.textContent = '[' + entry.time + '] ' + entry.text;
      div.setAttribute('data-type', entry.type);
      container.appendChild(div);

      _logCount++;
      while (_logCount > _MAX_LOGS && container.firstChild) {
        container.removeChild(container.firstChild);
        _logCount--;
      }
      container.scrollTop = container.scrollHeight;
    }
  }

  function _clearLog() {
    var container = document.getElementById('battle-log');
    if (container) {
      container.innerHTML = '';
      _logCount = 0;
    }
    _logEntries = [];
  }

  function _rebuildLogForFilter(filter) {
    var container = document.getElementById('battle-log');
    if (!container) return;
    container.innerHTML = '';
    _logCount = 0;

    for (var i = 0; i < _logEntries.length; i++) {
      var entry = _logEntries[i];
      if (filter === 'all' || filter === entry.type) {
        var div = document.createElement('div');
        div.className = 'log-entry ' + entry.type;
        div.textContent = '[' + entry.time + '] ' + entry.text;
        div.setAttribute('data-type', entry.type);
        container.appendChild(div);
        _logCount++;
      }
    }
    container.scrollTop = container.scrollHeight;
  }

  /* ---- WebSocket connection ---- */
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
      _addLog('System connected.', 'system', 0);
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
        if (msg.data) {
          _updateGameStatus(msg.data.running, msg.data.result);
          _updateTimer(msg.data.game_time);
          if (msg.data.boss) {
            _updatePhaseBadge(msg.data.boss.phase);
            _updateHeaderBossHp(msg.data.boss);
            _updateBossInfo(msg.data.boss);
          }
          _updateCharCards(msg.data.characters);
          var logs = msg.data.combat_log;
          if (logs && logs.length) {
            for (var i = 0; i < logs.length; i++) {
              var entry = logs[i];
              var logText = entry.text || entry.message || '';
              var logType = entry.type || null;
              if (logText) {
                // Use server-provided type if available, otherwise classify
                var finalType = (logType === 'ai_decision' || logType === 'ai_timeout')
                  ? logType
                  : _classifyLog(logText);
                _addLog(logText, finalType, msg.data.game_time);
              }
            }
          }
        }
      } else if (type === 'combat_log') {
        _emit('combat_log', msg.data);
        if (msg.data) {
          var text = msg.data.text || msg.data.message || JSON.stringify(msg.data);
          var serverType = msg.data.type || null;
          var cType = (serverType === 'ai_decision' || serverType === 'ai_timeout')
            ? serverType
            : _classifyLog(text);
          _addLog(text, cType, 0);
        }
      } else if (type === 'game_over') {
        _emit('game_over', msg.data);
        if (msg.data) {
          var result = msg.data.result || '';
          var message = msg.data.message || '';
          _addLog('=== ' + (result === 'victory' ? 'VICTORY!' : 'DEFEAT') + ' === ' + message, 'mech', 0);
          _updateGameStatus(false, result);
        }
      } else if (type === 'game_control') {
        if (msg.data) {
          var action = msg.data.action;
          if (action === 'started') {
            _updateGameStatus(true, null);
            _addLog('>>> \u6218\u6597\u5F00\u59CB! <<<', 'mech', 0);
          } else if (action === 'stopped') {
            _updateGameStatus(false, 'stopped');
          } else if (action === 'restarted') {
            _clearLog();
            _updateGameStatus(true, null);
            _addLog('>>> \u91CD\u65B0\u5F00\u59CB! <<<', 'mech', 0);
          }
        }
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
  }

  /* ---- Game control ---- */
  function startGame() { fetch('/api/start', { method: 'POST' }); }
  function stopGame()  { fetch('/api/stop', { method: 'POST' }); }
  function restartGame() { fetch('/api/restart', { method: 'POST' }); }

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

  /* ---- UI binding ---- */
  function _initUI() {
    // God command
    var input = document.getElementById('god-input');
    var btn = document.getElementById('god-send');
    if (input && btn) {
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

    // Game control buttons
    var startBtn = document.getElementById('btn-start');
    var stopBtn = document.getElementById('btn-stop');
    var restartBtn = document.getElementById('btn-restart');
    if (startBtn) startBtn.addEventListener('click', startGame);
    if (stopBtn) stopBtn.addEventListener('click', stopGame);
    if (restartBtn) restartBtn.addEventListener('click', restartGame);

    // Log tab filtering
    var tabs = document.querySelectorAll('.log-tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener('click', function () {
        var filter = this.getAttribute('data-filter');
        _activeLogFilter = filter;
        var allTabs = document.querySelectorAll('.log-tab');
        for (var j = 0; j < allTabs.length; j++) {
          allTabs[j].classList.remove('active');
        }
        this.classList.add('active');
        _rebuildLogForFilter(filter);
      });
    }

    // Quick command buttons
    var quickBtns = document.querySelectorAll('.quick-btn');
    for (var q = 0; q < quickBtns.length; q++) {
      quickBtns[q].addEventListener('click', function () {
        var cmd = this.getAttribute('data-cmd');
        var inp = document.getElementById('god-input');
        if (inp) {
          inp.value = cmd;
          inp.focus();
          if (cmd && cmd.charAt(cmd.length - 1) !== ' ') {
            sendGodCommand(cmd);
            inp.value = '';
          }
        }
      });
    }

    // Help button toggle
    var helpBtn = document.getElementById('cmd-help-btn');
    var helpPanel = document.getElementById('cmd-help-panel');
    if (helpBtn && helpPanel) {
      helpBtn.addEventListener('click', function () {
        helpPanel.classList.toggle('hidden');
      });
      document.addEventListener('click', function (e) {
        if (!helpBtn.contains(e.target) && !helpPanel.contains(e.target)) {
          helpPanel.classList.add('hidden');
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initUI);
  } else {
    _initUI();
  }

  return {
    connect: connect,
    send: send,
    sendGodCommand: sendGodCommand,
    startGame: startGame,
    stopGame: stopGame,
    restartGame: restartGame,
    on: on,
    off: off,
    isConnected: function () { return _connected; },
    isGameRunning: function () { return _gameRunning; }
  };
})();
