/**
 * WebSocket client for the AI Raid Battle game (V4).
 * Handles boss-strip + 5-player char-strip layout, AI Log panel,
 * tactical commands, and battle log filtering by role.
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
    boss: '\u{1F525}',   // fire
    tank: '\u{1F6E1}',   // shield
    healer: '\u{2695}',  // medical
    mage: '\u{1F52E}',   // crystal ball
    rogue: '\u{1F5E1}',  // dagger
    hunter: '\u{1F3F9}'  // bow
  };

  var ROLE_NAMES = {
    boss: 'BOSS',
    tank: '\u5766\u514B',
    healer: '\u6CBB\u7597',
    mage: '\u6CD5\u5E08',
    rogue: '\u76D7\u8D3C',
    hunter: '\u730E\u4EBA'
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
      el.textContent = connected ? '\u5DF2\u8FDE\u63A5' : '\u672A\u8FDE\u63A5';
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
        badge.textContent = result === 'victory' ? '\u80DC\u5229!' : '\u5931\u8D25';
        badge.className = result === 'victory' ? 'victory' : 'defeat';
      } else if (running) {
        badge.textContent = '\u6218\u6597\u4E2D';
        badge.className = 'fighting';
      } else {
        badge.textContent = '\u7B49\u5F85\u4E2D';
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

  /* ---- Boss Card (new structure) ---- */
  function _updateBossCard(bossCard) {
    if (!bossCard) return;
    var card = document.getElementById('card-boss');
    if (!card) return;

    var alive = bossCard.alive !== false && bossCard.hp > 0;
    if (alive) {
      card.classList.remove('dead');
    } else {
      card.classList.add('dead');
    }

    // Name (new: .boss-name instead of .card-name)
    var nameEl = card.querySelector('.boss-name');
    if (nameEl) nameEl.textContent = bossCard.name || 'BOSS';

    // Source tag
    _updateSourceTag(card, bossCard);

    // HP bar
    var hpPct = bossCard.max_hp > 0 ? (bossCard.hp / bossCard.max_hp) : 0;
    var hpFill = card.querySelector('.hp-fill');
    var hpText = card.querySelector('.boss-hp-text');
    if (hpFill) {
      hpFill.style.width = (hpPct * 100) + '%';
      hpFill.className = 'bar-fill hp-fill' + (hpPct > 0.6 ? '' : hpPct > 0.3 ? ' mid' : ' low');
    }
    if (hpText) {
      var pctDisplay = Math.round(hpPct * 100);
      hpText.textContent = bossCard.hp + '/' + bossCard.max_hp + ' (' + pctDisplay + '%)';
    }

    // Boss badges (phase, adds, enrage) - Chinese text
    var badgesEl = card.querySelector('.boss-badges');
    if (badgesEl) {
      var bhtml = '';
      bhtml += '<span class="boss-badge phase-badge">P' + (bossCard.phase || 1) + '</span>';
      var addsCount = bossCard.adds_count || 0;
      if (addsCount > 0) {
        bhtml += '<span class="boss-badge adds-badge">\u5C0F\u602A:' + addsCount + '</span>';
      }
      if (bossCard.enraged) {
        bhtml += '<span class="boss-badge enrage-badge">\u72C2\u66B4!</span>';
      } else if (bossCard.enrage_timer !== null && bossCard.enrage_timer !== undefined) {
        bhtml += '<span class="boss-badge enrage-timer-badge">\u72C2\u66B4:' + Math.ceil(bossCard.enrage_timer) + 's</span>';
      }
      badgesEl.innerHTML = bhtml;
    }

    // Skill slots (shared function)
    _updateSkillSlots(card, bossCard);

    // Cast bar
    var castBarEl = card.querySelector('.card-cast-bar');
    if (castBarEl) {
      if (bossCard.casting) {
        castBarEl.classList.remove('hidden');
        var castFillEl = castBarEl.querySelector('.card-cast-fill');
        var castTextEl = castBarEl.querySelector('.card-cast-text');
        var totalCast = bossCard.casting.skill_name === '\u706D\u4E16\u4E4B\u708E' ? 3.0 : 2.0;
        var progress = Math.max(0, 1 - bossCard.casting.remaining / totalCast) * 100;
        if (castFillEl) castFillEl.style.width = progress + '%';
        if (castTextEl) castTextEl.textContent = bossCard.casting.skill_name + ' ' + bossCard.casting.remaining.toFixed(1) + 's';
      } else {
        castBarEl.classList.add('hidden');
      }
    }

    // Action / Reason / Buffs (in .boss-row-bottom)
    var actionEl = card.querySelector('.card-action');
    if (actionEl) {
      if (bossCard.last_action && bossCard.last_action.skill_name) {
        var src = bossCard.last_action.source || '';
        var srcIcon = src === 'ai' ? '\u{1F916}' : src === 'timeout' ? '\u23F1' : '\u2699';
        actionEl.textContent = srcIcon + ' ' + bossCard.last_action.skill_name + ' \u2192 ' + (bossCard.last_action.target || '');
        actionEl.className = 'card-action source-' + src;
      } else {
        actionEl.textContent = '';
        actionEl.className = 'card-action';
      }
    }
    var reasonEl = card.querySelector('.card-reason');
    if (reasonEl) {
      if (bossCard.last_action && bossCard.last_action.reason) {
        reasonEl.textContent = '\u{1F4AD} "' + bossCard.last_action.reason + '"';
      } else {
        reasonEl.textContent = '';
      }
    }

    // Buffs/Debuffs
    var buffsEl = card.querySelector('.card-buffs');
    if (buffsEl) {
      var bhtml2 = '';
      var debuffs = bossCard.debuffs || [];
      for (var d = 0; d < debuffs.length; d++) {
        bhtml2 += '<span class="debuff-item">' + debuffs[d].name + '(' + Math.ceil(debuffs[d].duration) + 's) </span>';
      }
      buffsEl.innerHTML = bhtml2 || '';
    }
  }

  /* ---- Character Cards (5 players) ---- */
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

    // Source tag
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

    // Skill slots
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

    // Instruction (god command highlight with flash)
    var instrEl = card.querySelector('.card-instruction');
    if (instrEl) {
      var instrText = '';
      if (c.last_action && c.last_action.instruction) {
        instrText = c.last_action.instruction;
      }
      if (instrText) {
        var oldText = instrEl.getAttribute('data-last') || '';
        instrEl.textContent = '\u{1F4E5} \u6307\u4EE4: "' + instrText + '"';
        instrEl.style.display = '';
        if (instrText !== oldText) {
          instrEl.classList.remove('flash');
          void instrEl.offsetWidth; // force reflow
          instrEl.classList.add('flash');
          instrEl.setAttribute('data-last', instrText);
        }
      } else {
        instrEl.textContent = '';
        instrEl.style.display = 'none';
      }
    }

    // Action
    var actionEl = card.querySelector('.card-action');
    if (actionEl) {
      if (c.last_action && c.last_action.skill_name) {
        var actionSource = c.last_action.source || '';
        var sourceIcon = actionSource === 'ai' ? '\u{1F916}' : actionSource === 'timeout' ? '\u23F1' : '\u2699';
        actionEl.textContent = sourceIcon + ' ' + c.last_action.skill_name + ' \u2192 ' + (c.last_action.target || '');
        actionEl.className = 'card-action source-' + actionSource;
      } else {
        actionEl.textContent = '';
        actionEl.className = 'card-action';
      }
    }

    // Reason
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

  /* ---- Source Tag ---- */
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
      tag.textContent = '\u23F1 \u8D85\u65F6';
      tag.className = 'source-tag timeout';
    } else if (la && la.source === 'auto') {
      tag.textContent = '\u2699 \u81EA\u52A8';
      tag.className = 'source-tag auto';
    } else {
      tag.textContent = '\u23F3 \u7B49\u5F85\u4E2D';
      tag.className = 'source-tag waiting';
    }
  }

  /* ---- Skill Slots (dynamic, show ALL skills) ---- */
  function _updateSkillSlots(card, charData) {
    var skills = charData.skills || [];
    var cooldowns = charData.cooldowns || {};
    var lastAction = charData.last_action;
    var skillBar = card.querySelector('.skill-bar');
    if (!skillBar) return;
    var now = Date.now() / 1000;

    // Dynamically adjust slot count
    var slots = skillBar.querySelectorAll('.skill-slot');
    while (slots.length < skills.length) {
      var s = document.createElement('div');
      s.className = 'skill-slot';
      s.innerHTML = '<span class="skill-icon"></span><span class="cd-text"></span>';
      skillBar.appendChild(s);
      slots = skillBar.querySelectorAll('.skill-slot');
    }
    while (slots.length > skills.length) {
      skillBar.removeChild(skillBar.lastElementChild);
      slots = skillBar.querySelectorAll('.skill-slot');
    }

    for (var i = 0; i < skills.length; i++) {
      var skill = skills[i];
      var slot = slots[i];
      if (!slot) continue;
      var cd = cooldowns[String(skill.id)] || 0;
      var isAuto = !!skill.auto;
      var isActive = lastAction && lastAction.source === 'ai'
        && lastAction.skill_name === skill.name
        && (now - lastAction.time) < 2;

      slot.className = 'skill-slot';
      if (isAuto) slot.classList.add('auto-skill');

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
        if (cdTextEl) cdTextEl.textContent = isAuto ? '\u81EA\u52A8' : '\u5C31\u7EEA';
      }
      slot.title = skill.name + (isAuto ? ' [\u81EA\u52A8]' : '') + '\n' + (skill.description || '') + (cd > 0 ? '\nCD: ' + Math.ceil(cd) + 's' : '');
    }
  }

  /* ---- AI Log Panel ---- */
  function _updateAiLog(aiLog) {
    var container = document.getElementById('ai-log');
    if (!container || !aiLog || !aiLog.length) return;

    container.innerHTML = '';

    // Separate boss and player entries
    var bossEntries = [];
    var playerEntries = [];
    for (var i = 0; i < aiLog.length; i++) {
      var entry = aiLog[i];
      if (!entry.last_response) continue;
      if (entry.is_boss) {
        bossEntries.push(entry);
      } else {
        playerEntries.push(entry);
      }
    }

    // Boss section
    if (bossEntries.length > 0) {
      var bossHeader = document.createElement('div');
      bossHeader.className = 'ai-log-section-header boss-section';
      bossHeader.textContent = '\u{1F525} Boss AI';
      container.appendChild(bossHeader);
      for (var b = 0; b < bossEntries.length; b++) {
        _renderAiLogEntry(container, bossEntries[b]);
      }
    }

    // Player section
    if (playerEntries.length > 0) {
      var playerHeader = document.createElement('div');
      playerHeader.className = 'ai-log-section-header player-section';
      playerHeader.textContent = '\u2694\uFE0F \u56E2\u961F AI';
      container.appendChild(playerHeader);
      for (var p = 0; p < playerEntries.length; p++) {
        _renderAiLogEntry(container, playerEntries[p]);
      }
    }
  }

  function _renderAiLogEntry(container, entry) {
    var role = entry.role || '';
    var div = document.createElement('div');
    div.className = 'ai-log-entry ' + role + '-entry';

    // Header
    var icon = ROLE_ICONS[role] || '';
    var name = entry.name || entry.id || role;
    var respTime = entry.last_response.time ? _formatTimeSince(entry.last_response.time) : '';

    var html = '<div class="ai-log-header">';
    html += '<span class="ai-log-name">' + icon + ' ' + _escHtml(name) + '</span>';
    html += '<span class="ai-log-time">' + respTime + '</span>';
    html += '</div>';

    // Query (truncated)
    if (entry.last_query) {
      var queryPreview = entry.last_query.substring(0, 200);
      if (entry.last_query.length > 200) queryPreview += '...';
      html += '<div class="ai-log-query">Q: ' + _escHtml(queryPreview) + '</div>';
    }

    // Response
    if (entry.last_response.tool_name) {
      var target = entry.last_response.target || '';
      html += '<div class="ai-log-response">A: ' + _escHtml(entry.last_response.tool_name) + ' \u2192 ' + _escHtml(target) + '</div>';
    }

    // Reason
    if (entry.last_response.reason) {
      html += '<div class="ai-log-reason">\u{1F4AD} "' + _escHtml(entry.last_response.reason) + '"</div>';
    }

    div.innerHTML = html;
    container.appendChild(div);
  }

  function _formatTimeSince(timestamp) {
    var now = Date.now() / 1000;
    var diff = Math.floor(now - timestamp);
    if (diff < 1) return '\u521A\u521A';
    if (diff < 60) return diff + 's\u524D';
    return Math.floor(diff / 60) + 'm\u524D';
  }

  function _escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ---- Log classification by role ---- */
  function _classifyLogByRole(text) {
    if (!text) return 'system';
    // Commands
    if (/\[God\]|\u4E0A\u5E1D\u6307\u4EE4|\[DM\]/.test(text)) return 'cmd';
    // System
    if (/===|>>>|\u6218\u6597\u5F00\u59CB|\u6218\u6597\u7ED3\u675F|System|connected/.test(text)) return 'system';
    // Role detection (check first 30 chars, then full text)
    var head = text.substring(0, 30);
    if (/\u62C9\u683C\u7EB3\u7F57\u65AF|\u7194\u706B\u4E4B\u738B|boss|BOSS|\u7194\u5CA9\u5143\u7D20|Phase|\[P[123]\]|\u72C2\u66B4/.test(head)) return 'boss';
    if (/\u514B\u52B3\u5FB7|\u5723\u9A91\u58EB|tank/.test(head)) return 'tank';
    if (/\u7D22\u5948\u7279|\u7267\u5E08|healer/.test(head)) return 'healer';
    if (/\u6B27\u5E15\u65AF|\u6CD5\u5E08|mage/.test(head)) return 'mage';
    if (/\u6D77\u9177|\u76D7\u8D3C|rogue/.test(head)) return 'rogue';
    if (/\u963F\u5C14\u6CD5|\u730E\u4EBA|hunter/.test(head)) return 'hunter';
    // Full text fallback
    if (/\u62C9\u683C\u7EB3\u7F57\u65AF|boss|\u7194\u5CA9|\u88C2\u96D9|\u9677\u9631|\u706D\u4E16|\u70C8\u7130\u98CE\u66B4|\u53EC\u5524|\u72C2\u66B4|Phase/.test(text)) return 'boss';
    if (/\u514B\u52B3\u5FB7|\u5723\u9A91\u58EB|\u5632\u8BBD|\u76FE\u5899|\u82F1\u52C7\u6253\u51FB|\u7834\u7532/.test(text)) return 'tank';
    if (/\u7D22\u5948\u7279|\u7267\u5E08|\u6CBB\u7597\u672F|\u7FA4\u4F53\u6CBB\u7597|\u9A71\u6563|\u590D\u6D3B/.test(text)) return 'healer';
    if (/\u6B27\u5E15\u65AF|\u6CD5\u5E08|\u706B\u7403|\u66B4\u98CE\u96EA|\u51B0\u51BB|\u6CD5\u672F\u5C4F\u969C/.test(text)) return 'mage';
    if (/\u6D77\u9177|\u76D7\u8D3C|\u80CC\u523A|\u6BD2\u5203|\u95EA\u907F|\u81F4\u547D\u8FDE\u51FB/.test(text)) return 'rogue';
    if (/\u963F\u5C14\u6CD5|\u730E\u4EBA|\u5C04\u51FB|\u591A\u91CD|\u5370\u8BB0|\u6CBB\u7597\u4E4B\u98CE/.test(text)) return 'hunter';
    return 'system';
  }

  /* ---- Battle log ---- */
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
    // Also clear AI log
    var aiLog = document.getElementById('ai-log');
    if (aiLog) aiLog.innerHTML = '';
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
          }
          // Update boss card from boss_card data
          if (msg.data.boss_card) {
            _updateBossCard(msg.data.boss_card);
          }
          // Update player cards
          _updateCharCards(msg.data.characters);
          // Update AI Log
          if (msg.data.ai_log) {
            _updateAiLog(msg.data.ai_log);
          }
          // Process combat logs
          var logs = msg.data.combat_log;
          if (logs && logs.length) {
            for (var i = 0; i < logs.length; i++) {
              var entry = logs[i];
              var logText = entry.text || entry.message || '';
              if (logText) {
                var finalType = _classifyLogByRole(logText);
                _addLog(logText, finalType, msg.data.game_time);
              }
            }
          }
        }
      } else if (type === 'combat_log') {
        _emit('combat_log', msg.data);
        if (msg.data) {
          var text = msg.data.text || msg.data.message || JSON.stringify(msg.data);
          var cType = _classifyLogByRole(text);
          _addLog(text, cType, 0);
        }
      } else if (type === 'game_over') {
        _emit('game_over', msg.data);
        if (msg.data) {
          var result = msg.data.result || '';
          var message = msg.data.message || '';
          _addLog('=== ' + (result === 'victory' ? '\u80DC\u5229!' : '\u5931\u8D25') + ' === ' + message, 'system', 0);
          _updateGameStatus(false, result);
        }
      } else if (type === 'game_control') {
        if (msg.data) {
          var action = msg.data.action;
          if (action === 'started') {
            _updateGameStatus(true, null);
            _addLog('>>> \u6218\u6597\u5F00\u59CB! <<<', 'system', 0);
          } else if (action === 'stopped') {
            _updateGameStatus(false, 'stopped');
          } else if (action === 'restarted') {
            _clearLog();
            _updateGameStatus(true, null);
            _addLog('>>> \u91CD\u65B0\u5F00\u59CB! <<<', 'system', 0);
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

    // Main log tab switching (BATTLE | AI)
    var mainTabs = document.querySelectorAll('.log-main-tab');
    for (var m = 0; m < mainTabs.length; m++) {
      mainTabs[m].addEventListener('click', function () {
        var panel = this.getAttribute('data-panel');
        var allMainTabs = document.querySelectorAll('.log-main-tab');
        for (var k = 0; k < allMainTabs.length; k++) {
          allMainTabs[k].classList.remove('active');
        }
        this.classList.add('active');

        // Toggle panels
        var battlePanel = document.getElementById('battle-log-panel');
        var aiPanel = document.getElementById('ai-log-panel');
        if (panel === 'battle') {
          if (battlePanel) battlePanel.classList.add('active');
          if (aiPanel) aiPanel.classList.remove('active');
        } else {
          if (battlePanel) battlePanel.classList.remove('active');
          if (aiPanel) aiPanel.classList.add('active');
        }
      });
    }

    // Battle log sub-tab filtering
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

    // Tactical quick command buttons (send immediately, with visual feedback)
    var quickBtns = document.querySelectorAll('.quick-btn');
    for (var q = 0; q < quickBtns.length; q++) {
      quickBtns[q].addEventListener('click', function () {
        var cmd = this.getAttribute('data-cmd');
        if (cmd) {
          sendGodCommand(cmd);
          this.classList.add('sent');
          var btnRef = this;
          setTimeout(function() { btnRef.classList.remove('sent'); }, 300);
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
