/**
 * WebSocket client for the AI Raid Battle game (V5).
 * Three-column layout: Boss fused into Header, 5 vertical char cards,
 * 5 player AI chat windows. No more Boss card or AI log panel.
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
    tank: '坦克',
    healer: '治疗',
    mage: '法师',
    rogue: '盗贼',
    hunter: '猎人'
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
      el.textContent = connected ? '已连接' : '未连接';
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
        badge.textContent = result === 'victory' ? '胜利!' : '失败';
        badge.className = result === 'victory' ? 'victory' : 'defeat';
      } else if (running) {
        badge.textContent = '战斗中';
        badge.className = 'fighting';
      } else {
        badge.textContent = '等待中';
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
    var names = { 1: 'P1 觉醒', 2: 'P2 狂怒', 3: 'P3 灭世' };
    el.textContent = names[phase] || 'P' + phase;
    el.className = phase >= 3 ? 'p3' : phase >= 2 ? 'p2' : '';
  }

  /* ---- Boss Header (fused: HP + AI decision + cast + badges) ---- */
  function _updateBossHeader(bossCard, bossAiEntry) {
    if (!bossCard) return;

    // Boss name
    var nameEl = document.getElementById('header-boss-name');
    if (nameEl) nameEl.textContent = bossCard.name || '拉格纳罗斯';

    // HP bar
    var hpPct = bossCard.max_hp > 0 ? (bossCard.hp / bossCard.max_hp) : 0;
    var fill = document.getElementById('header-boss-hp-fill');
    var text = document.getElementById('header-boss-hp-text');
    if (fill) fill.style.width = Math.max(0, Math.min(100, hpPct * 100)) + '%';
    if (text) text.textContent = bossCard.hp + '/' + bossCard.max_hp + ' (' + Math.round(hpPct * 100) + '%)';

    // Boss AI decision (Row 2) — use skill_name, not tool_name
    var actionEl = document.getElementById('boss-ai-action');
    var reasonEl = document.getElementById('boss-ai-reason');
    if (actionEl) {
      if (bossCard.last_action && bossCard.last_action.skill_name) {
        var src = bossCard.last_action.source || '';
        var srcIcon = src === 'ai' ? '\u{1F916}' : src === 'timeout' ? '\u23F1' : '\u2699';
        var targetDisp = _targetName(bossCard.last_action.target || '');
        actionEl.textContent = srcIcon + ' ' + bossCard.last_action.skill_name + (targetDisp ? ' \u2192 ' + targetDisp : '');
      } else {
        actionEl.textContent = '';
      }
    }
    if (reasonEl) {
      if (bossCard.last_action && bossCard.last_action.reason) {
        reasonEl.textContent = '\u{1F4AD} "' + bossCard.last_action.reason + '"';
      } else if (bossAiEntry && bossAiEntry.last_response && bossAiEntry.last_response.reason) {
        reasonEl.textContent = '\u{1F4AD} "' + bossAiEntry.last_response.reason + '"';
      } else {
        reasonEl.textContent = '';
      }
    }

    // Cast indicator (Row 2)
    var castEl = document.getElementById('header-cast-indicator');
    if (castEl) {
      if (bossCard.casting) {
        castEl.classList.remove('hidden');
        castEl.textContent = '\u23F3' + bossCard.casting.skill_name + ' ' + bossCard.casting.remaining.toFixed(1) + 's';
      } else {
        castEl.classList.add('hidden');
      }
    }

    // Boss badges (Row 2)
    var badgesEl = document.getElementById('boss-badges');
    if (badgesEl) {
      var bhtml = '';
      var addsCount = bossCard.adds_count || 0;
      if (addsCount > 0) {
        bhtml += '<span class="boss-badge adds-badge">小怪:' + addsCount + '</span>';
      }
      // Fire shield indicator
      var buffs = bossCard.buffs || [];
      for (var bi = 0; bi < buffs.length; bi++) {
        if (buffs[bi].id === 'fire_shield') {
          bhtml += '<span class="boss-badge fire-shield-badge">🔥盾:' + Math.ceil(buffs[bi].duration) + 's</span>';
        }
      }
      if (bossCard.enraged) {
        bhtml += '<span class="boss-badge enrage-badge">狂暴!</span>';
      } else if (bossCard.enrage_timer !== null && bossCard.enrage_timer !== undefined) {
        bhtml += '<span class="boss-badge enrage-timer-badge">狂暴:' + Math.ceil(bossCard.enrage_timer) + 's</span>';
      }
      badgesEl.innerHTML = bhtml;
    }
  }

  /* ---- Character Cards (5 players, no instruction/action/reason - moved to AI chat) ---- */
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
      tag.textContent = '☠ 已阵亡';
      tag.className = 'source-tag dead';
    } else if (la && la.source === 'ai') {
      tag.textContent = '🤖 AI';
      tag.className = 'source-tag ai-decision';
    } else if (la && la.source === 'timeout') {
      tag.textContent = '⏱ 超时';
      tag.className = 'source-tag timeout';
    } else if (la && la.source === 'auto') {
      tag.textContent = '⚙ 自动';
      tag.className = 'source-tag auto';
    } else {
      tag.textContent = '⏳ 等待';
      tag.className = 'source-tag waiting';
    }
  }

  /* ---- Skill Slots (dynamic) ---- */
  function _updateSkillSlots(card, charData) {
    var skills = charData.skills || [];
    var cooldowns = charData.cooldowns || {};
    var lastAction = charData.last_action;
    var skillBar = card.querySelector('.skill-bar');
    if (!skillBar) return;
    var now = Date.now() / 1000;

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
        if (cdTextEl) cdTextEl.textContent = '★AI';
      } else if (cd > 0) {
        slot.classList.add('on-cooldown');
        if (cdTextEl) cdTextEl.textContent = Math.ceil(cd) + 's';
      } else {
        slot.classList.add('ready');
        if (cdTextEl) cdTextEl.textContent = isAuto ? '自动' : '就绪';
      }
      slot.title = skill.name + (isAuto ? ' [自动]' : '') + '\n' + (skill.description || '') + (cd > 0 ? '\nCD: ' + Math.ceil(cd) + 's' : '');
    }
  }

  /* ---- Target display name mapping ---- */
  var TARGET_NAMES = {
    boss: 'Boss', tank: '坦克', healer: '治疗',
    mage: '法师', rogue: '盗贼', hunter: '猎人'
  };

  function _targetName(t) {
    if (!t) return '';
    if (TARGET_NAMES[t]) return TARGET_NAMES[t];
    if (t.indexOf('add_') === 0) return '小怪' + t.replace('add_', '#');
    return t;
  }

  /* ---- AI Chat Windows (5 player windows + Boss strategy panel) ---- */
  function _updateAiChatWindows(aiLog) {
    if (!aiLog || !aiLog.length) return;

    var bossAiEntry = null;

    for (var i = 0; i < aiLog.length; i++) {
      var entry = aiLog[i];
      var isQuerying = !!entry.querying;

      if (entry.is_boss) {
        bossAiEntry = entry;
        if (entry.last_response) {
          _updateBossStrategyPanel(entry);
        }
        // Boss querying indicator on strategy panel
        var bossPanel = document.getElementById('boss-strategy-panel');
        if (bossPanel) {
          if (isQuerying) {
            bossPanel.classList.add('querying');
          } else {
            bossPanel.classList.remove('querying');
          }
        }
        continue;
      }

      // Player AI -> update corresponding chat window + char card
      var role = entry.role || '';
      var window_el = document.getElementById('ai-chat-' + role);
      var card_el = document.getElementById('card-' + role);

      // Querying state — toggle class on both AI chat window and char card
      if (window_el) {
        if (isQuerying) {
          window_el.classList.add('querying');
        } else {
          window_el.classList.remove('querying');
        }
      }
      if (card_el) {
        if (isQuerying) {
          card_el.classList.add('querying');
        } else {
          card_el.classList.remove('querying');
        }
      }

      if (!entry.last_response || !window_el) continue;

      // Time
      var timeEl = window_el.querySelector('.ai-chat-time');
      if (timeEl) {
        timeEl.textContent = entry.last_response.time ? _formatTimeSince(entry.last_response.time) : '';
      }

      // Query (more info, multi-line friendly, smaller font)
      var queryEl = window_el.querySelector('.ai-chat-query');
      if (queryEl) {
        if (entry.last_query) {
          var queryPreview = entry.last_query.substring(0, 800);
          if (entry.last_query.length > 800) queryPreview += '...';
          queryEl.textContent = 'Q: ' + queryPreview;
        } else {
          queryEl.textContent = '';
        }
      }

      // Response — show skill name + target name (not tool_name)
      var respEl = window_el.querySelector('.ai-chat-response');
      if (respEl) {
        var skillName = entry.last_response.skill_name || entry.last_response.tool_name || '';
        if (skillName) {
          var target = entry.last_response.target || '';
          var targetDisplay = _targetName(target);
          respEl.innerHTML = 'A: <span class="skill-label">' + _escHtml(skillName) + '</span>'
            + (targetDisplay ? ' \u2192 <span class="target-label">' + _escHtml(targetDisplay) + '</span>' : '');
        } else {
          respEl.innerHTML = '';
        }
      }

      // Reason — multi-line with word wrap
      var reasonEl = window_el.querySelector('.ai-chat-reason');
      if (reasonEl) {
        if (entry.last_response.reason) {
          reasonEl.textContent = '\u{1F4AD} "' + entry.last_response.reason + '"';
        } else {
          reasonEl.textContent = '';
        }
      }
    }

    return bossAiEntry;
  }

  /* ---- Boss Strategy Panel (prominent display in left column) ---- */
  function _updateBossStrategyPanel(bossEntry) {
    var actionEl = document.getElementById('boss-strategy-action');
    var reasonEl = document.getElementById('boss-strategy-reason');
    if (!actionEl || !reasonEl) return;

    var resp = bossEntry.last_response;
    if (!resp) {
      actionEl.textContent = '';
      reasonEl.textContent = '';
      return;
    }

    var skillName = resp.skill_name || resp.tool_name || '';
    var target = resp.target || '';
    var targetDisplay = _targetName(target);

    if (skillName) {
      actionEl.textContent = '\u{1F916} ' + skillName + (targetDisplay ? ' \u2192 ' + targetDisplay : '');
    } else {
      actionEl.textContent = '';
    }

    if (resp.reason) {
      reasonEl.textContent = '\u{1F4AD} ' + resp.reason;
    } else {
      reasonEl.textContent = '';
    }
  }

  function _formatTimeSince(timestamp) {
    var now = Date.now() / 1000;
    var diff = Math.floor(now - timestamp);
    if (diff < 1) return '刚刚';
    if (diff < 60) return diff + 's前';
    return Math.floor(diff / 60) + 'm前';
  }

  function _escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ---- Log classification by role ---- */
  function _classifyLogByRole(text) {
    if (!text) return 'system';
    if (/\[God\]|团长指令|\[DM\]/.test(text)) return 'cmd';
    if (/===|>>>|战斗开始|战斗结束|System|connected/.test(text)) return 'system';
    var head = text.substring(0, 30);
    if (/拉格纳罗斯|熔火之王|boss|BOSS|熔岩元素|Phase|\[P[123]\]|狂暴|熔岩灼烧|禁疗|火焰盾|熔火突刺/.test(head)) return 'boss';
    if (/克劳德|圣骑士|tank/.test(head)) return 'tank';
    if (/索奈特|牧师|healer/.test(head)) return 'healer';
    if (/欧帕斯|法师|mage/.test(head)) return 'mage';
    if (/海酷|盗贼|rogue/.test(head)) return 'rogue';
    if (/阿尔法|猎人|hunter/.test(head)) return 'hunter';
    if (/拉格纳罗斯|boss|熔岩|裂隙|陷阱|灭世|烈焰风暴|召唤|狂暴|Phase|禁疗|火焰盾|熔火突刺|环境灼烧/.test(text)) return 'boss';
    if (/克劳德|圣骑士|嘲讽|盾墙|英勇打击|破甲/.test(text)) return 'tank';
    if (/索奈特|牧师|治疗术|群体治疗|驱散|复活/.test(text)) return 'healer';
    if (/欧帕斯|法师|火球|暴风雪|冰冻|法术屏障/.test(text)) return 'mage';
    if (/海酷|盗贼|背刺|毒刃|闪避|致命连击/.test(text)) return 'rogue';
    if (/阿尔法|猎人|射击|多重|印记|治疗之风/.test(text)) return 'hunter';
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

    // Clear Header Row2 (Boss AI)
    var bossAction = document.getElementById('boss-ai-action');
    var bossReason = document.getElementById('boss-ai-reason');
    var castInd = document.getElementById('header-cast-indicator');
    var badges = document.getElementById('boss-badges');
    if (bossAction) bossAction.textContent = '';
    if (bossReason) bossReason.textContent = '';
    if (castInd) castInd.classList.add('hidden');
    if (badges) badges.innerHTML = '';

    // Clear Boss Strategy Panel
    var bsAction = document.getElementById('boss-strategy-action');
    var bsReason = document.getElementById('boss-strategy-reason');
    if (bsAction) bsAction.textContent = '';
    if (bsReason) bsReason.textContent = '';

    // Clear 5 AI chat windows
    var roles = ['tank', 'healer', 'mage', 'rogue', 'hunter'];
    for (var i = 0; i < roles.length; i++) {
      var win = document.getElementById('ai-chat-' + roles[i]);
      if (!win) continue;
      var q = win.querySelector('.ai-chat-query');
      var r = win.querySelector('.ai-chat-response');
      var rsn = win.querySelector('.ai-chat-reason');
      var t = win.querySelector('.ai-chat-time');
      if (q) q.textContent = '';
      if (r) r.textContent = '';
      if (rsn) rsn.textContent = '';
      if (t) t.textContent = '';
    }
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
          }
          // Update Boss Header (fused)
          var bossAiEntry = null;
          if (msg.data.ai_log) {
            bossAiEntry = _updateAiChatWindows(msg.data.ai_log);
          }
          if (msg.data.boss_card) {
            _updateBossHeader(msg.data.boss_card, bossAiEntry);
          }
          // Update player cards
          _updateCharCards(msg.data.characters);
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
          _addLog('=== ' + (result === 'victory' ? '胜利!' : '失败') + ' === ' + message, 'system', 0);
          _updateGameStatus(false, result);
        }
      } else if (type === 'game_control') {
        if (msg.data) {
          var action = msg.data.action;
          if (action === 'started') {
            _updateGameStatus(true, null);
            _addLog('>>> 战斗开始! <<<', 'system', 0);
          } else if (action === 'stopped') {
            _updateGameStatus(false, 'stopped');
          } else if (action === 'reset') {
            // Reset: clear logs, set status to "waiting", do NOT auto-start
            _clearLog();
            _updateGameStatus(false, null);
            _updateTimer(0);
            _updatePhaseBadge(1);
            // Reset Header boss HP bar
            var hpFill = document.getElementById('header-boss-hp-fill');
            var hpText = document.getElementById('header-boss-hp-text');
            if (hpFill) hpFill.style.width = '100%';
            if (hpText) hpText.textContent = '';
            _addLog('✔ 已重置，点击"开始"开战。', 'system', 0);
            _emit('game_reset', null);
          } else if (action === 'restarted') {
            // Legacy support: treat as reset + start
            _clearLog();
            _updateGameStatus(true, null);
            _addLog('>>> 重新开始! <<<', 'system', 0);
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

    // Tactical quick command buttons
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
