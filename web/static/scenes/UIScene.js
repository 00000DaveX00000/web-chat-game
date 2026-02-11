/**
 * UIScene - Overlay UI layer for health bars, skill CDs, buffs, and boss info.
 * Runs in parallel with BattleScene.
 */
var UIScene = new Phaser.Class({
  Extends: Phaser.Scene,

  initialize: function UIScene() {
    Phaser.Scene.call(this, { key: 'UIScene' });
    this._bossBar = null;
    this._bossNameText = null;
    this._bossPhaseText = null;
    this._charPanels = {};
    this._lastState = null;
  },

  create: function () {
    // Boss HP bar at top
    this._createBossBar();

    // Character panels at bottom
    this._charPanelGroup = this.add.container(0, 0);

    // Listen for state changes from BattleScene
    var self = this;
    this.events.on('state_changed', function (data) {
      self._onStateUpdate(data);
    });
  },

  /* ===== Boss HP Bar ===== */
  _createBossBar: function () {
    var x = 230;
    var y = 16;
    var w = 500;
    var h = 24;

    // Background
    var bg = this.add.rectangle(x, y, w, h, 0x222222).setOrigin(0, 0);
    bg.setStrokeStyle(2, 0x444466);

    // HP fill
    var fill = this.add.rectangle(x + 2, y + 2, w - 4, h - 4, 0xcc2222).setOrigin(0, 0);

    // Phase indicator
    var phaseText = this.add.text(x + w + 10, y + 4, 'P1', {
      fontFamily: '"Press Start 2P"',
      fontSize: '12px',
      color: '#ffcc00'
    });

    // Boss name
    var nameText = this.add.text(x - 4, y + 4, 'BOSS', {
      fontFamily: '"Press Start 2P"',
      fontSize: '10px',
      color: '#ff4444',
      align: 'right'
    }).setOrigin(1, 0);

    // HP text in bar
    var hpText = this.add.text(x + w / 2, y + 5, '100%', {
      fontFamily: '"Press Start 2P"',
      fontSize: '10px',
      color: '#ffffff',
      stroke: '#000000',
      strokeThickness: 2
    }).setOrigin(0.5, 0);

    this._bossBar = { bg: bg, fill: fill, x: x, y: y, w: w, h: h };
    this._bossPhaseText = phaseText;
    this._bossNameText = nameText;
    this._bossHpText = hpText;
  },

  /* ===== Character Panels ===== */
  _createCharPanel: function (charData, index) {
    var panelW = 160;
    var panelH = 80;
    var gap = 12;
    var totalW = 5 * panelW + 4 * gap;
    var startX = (960 - totalW) / 2;
    var x = startX + index * (panelW + gap);
    var y = 556;

    var container = this.add.container(x, y);

    // Panel background
    var bg = this.add.rectangle(0, 0, panelW, panelH, 0x111128, 0.9).setOrigin(0, 0);
    bg.setStrokeStyle(2, 0x2a2a4a);
    container.add(bg);

    // Role icon (small sprite)
    var roleKey = charData.role || 'tank';
    var icon = this.add.sprite(16, 16, roleKey).setScale(0.8).setOrigin(0, 0);
    container.add(icon);

    // Name
    var name = this.add.text(42, 4, charData.name || roleKey, {
      fontFamily: '"Press Start 2P"',
      fontSize: '7px',
      color: '#ccccdd'
    });
    container.add(name);

    // HP bar
    var hpBg = this.add.rectangle(42, 18, 108, 10, 0x333333).setOrigin(0, 0);
    hpBg.setStrokeStyle(1, 0x555555);
    container.add(hpBg);
    var hpFill = this.add.rectangle(43, 19, 106, 8, 0x33cc33).setOrigin(0, 0);
    container.add(hpFill);

    // HP text
    var hpText = this.add.text(96, 19, '100%', {
      fontFamily: '"Press Start 2P"',
      fontSize: '6px',
      color: '#ffffff',
      stroke: '#000000',
      strokeThickness: 1
    }).setOrigin(0.5, 0);
    container.add(hpText);

    // Mana bar
    var mpBg = this.add.rectangle(42, 31, 108, 8, 0x222244).setOrigin(0, 0);
    mpBg.setStrokeStyle(1, 0x333366);
    container.add(mpBg);
    var mpFill = this.add.rectangle(43, 32, 106, 6, 0x3366ff).setOrigin(0, 0);
    container.add(mpFill);

    // Mana text
    var mpText = this.add.text(96, 31, '100%', {
      fontFamily: '"Press Start 2P"',
      fontSize: '5px',
      color: '#aaccff',
      stroke: '#000000',
      strokeThickness: 1
    }).setOrigin(0.5, 0);
    container.add(mpText);

    // Buff/Debuff row
    var buffContainer = this.add.container(42, 44);
    container.add(buffContainer);

    // Skill CD indicators
    var cdContainer = this.add.container(4, 56);
    container.add(cdContainer);

    this._charPanelGroup.add(container);

    return {
      container: container,
      bg: bg,
      icon: icon,
      hpFill: hpFill,
      hpText: hpText,
      mpFill: mpFill,
      mpText: mpText,
      buffContainer: buffContainer,
      cdContainer: cdContainer,
      panelW: panelW
    };
  },

  /* ===== State Update ===== */
  _onStateUpdate: function (data) {
    if (!data) return;
    this._lastState = data;

    // Update boss bar
    if (data.boss) {
      this._updateBossBar(data.boss);
    }

    // Update character panels (dict: {id: charData})
    if (data.characters) {
      var chars = data.characters;
      var charKeys = Object.keys(chars);
      for (var i = 0; i < charKeys.length; i++) {
        var cid = charKeys[i];
        var c = chars[cid];
        if (!this._charPanels[cid]) {
          this._charPanels[cid] = this._createCharPanel(c, i);
        }
        this._updateCharPanel(c);
      }
    }
  },

  /* ===== Update Boss Bar ===== */
  _updateBossBar: function (boss) {
    var maxHp = boss.max_hp || boss.maxHp || 1;
    var hp = boss.hp || 0;
    var pct = Math.max(0, Math.min(1, hp / maxHp));
    var barW = this._bossBar.w - 4;

    // Animate HP bar
    this.tweens.add({
      targets: this._bossBar.fill,
      displayWidth: barW * pct,
      duration: 300,
      ease: 'Power2'
    });

    // Color transition
    var color;
    if (pct > 0.5) color = 0xcc2222;
    else if (pct > 0.25) color = 0xcc6622;
    else color = 0xff0000;
    this._bossBar.fill.setFillStyle(color);

    // Phase text
    var phase = boss.phase || 1;
    this._bossPhaseText.setText('P' + phase);

    // Name
    this._bossNameText.setText(boss.name || 'BOSS');

    // HP percentage
    this._bossHpText.setText(Math.round(pct * 100) + '%');
  },

  /* ===== Update Character Panel ===== */
  _updateCharPanel: function (charData) {
    var panel = this._charPanels[charData.id];
    if (!panel) return;

    var maxHp = charData.max_hp || charData.maxHp || 1;
    var hp = charData.hp || 0;
    var hpPct = Math.max(0, Math.min(1, hp / maxHp));

    var maxMp = charData.max_mana || charData.maxMana || 1;
    var mp = charData.mana || 0;
    var mpPct = Math.max(0, Math.min(1, mp / maxMp));

    // HP bar width & color
    var hpW = 106 * hpPct;
    this.tweens.add({
      targets: panel.hpFill,
      displayWidth: Math.max(0, hpW),
      duration: 300,
      ease: 'Power2'
    });

    var hpColor;
    if (hpPct > 0.6) hpColor = 0x33cc33;
    else if (hpPct > 0.3) hpColor = 0xcccc33;
    else hpColor = 0xcc3333;
    panel.hpFill.setFillStyle(hpColor);

    panel.hpText.setText(Math.round(hpPct * 100) + '%');

    // Mana bar
    var mpW = 106 * mpPct;
    this.tweens.add({
      targets: panel.mpFill,
      displayWidth: Math.max(0, mpW),
      duration: 300,
      ease: 'Power2'
    });
    panel.mpText.setText(Math.round(mpPct * 100) + '%');

    // Death state - dim the panel
    if (charData.alive === false || hp <= 0) {
      panel.bg.setFillStyle(0x1a0a0a, 0.9);
      panel.icon.setTint(0x444444);
      panel.icon.setAlpha(0.5);
    } else {
      panel.bg.setFillStyle(0x111128, 0.9);
      panel.icon.clearTint();
      panel.icon.setAlpha(1);
    }

    // Buffs/Debuffs
    this._updateBuffs(panel, charData.buffs || []);

    // Skill CDs
    this._updateSkillCDs(panel, charData.skill_cds || charData.skillCds || {});
  },

  /* ===== Buff/Debuff icons ===== */
  _updateBuffs: function (panel, buffs) {
    panel.buffContainer.removeAll(true);

    for (var i = 0; i < buffs.length && i < 6; i++) {
      var buff = buffs[i];
      var isDebuff = buff.is_debuff || buff.isDebuff || false;
      var color = isDebuff ? 0xff3333 : 0x33cc33;

      var icon = this.add.rectangle(i * 14, 0, 12, 12, color, 0.7).setOrigin(0, 0);
      icon.setStrokeStyle(1, isDebuff ? 0xff6666 : 0x66ff66);
      panel.buffContainer.add(icon);

      // Duration remaining
      if (buff.remaining !== undefined) {
        var dur = this.add.text(i * 14 + 6, 1, Math.ceil(buff.remaining).toString(), {
          fontFamily: '"Press Start 2P"',
          fontSize: '6px',
          color: '#ffffff',
          stroke: '#000000',
          strokeThickness: 1
        }).setOrigin(0.5, 0);
        panel.buffContainer.add(dur);
      }
    }
  },

  /* ===== Skill CD indicators ===== */
  _updateSkillCDs: function (panel, cds) {
    panel.cdContainer.removeAll(true);

    var keys = Object.keys(cds);
    for (var i = 0; i < keys.length && i < 4; i++) {
      var cdVal = cds[keys[i]];
      var ready = cdVal <= 0;
      var color = ready ? 0x33cc33 : 0x666666;

      var box = this.add.rectangle(i * 36, 0, 32, 16, color, 0.6).setOrigin(0, 0);
      box.setStrokeStyle(1, ready ? 0x66ff66 : 0x444444);
      panel.cdContainer.add(box);

      var label = ready ? 'RDY' : Math.ceil(cdVal) + 's';
      var txt = this.add.text(i * 36 + 16, 2, label, {
        fontFamily: '"Press Start 2P"',
        fontSize: '6px',
        color: ready ? '#33ff66' : '#aaaaaa',
        stroke: '#000000',
        strokeThickness: 1
      }).setOrigin(0.5, 0);
      panel.cdContainer.add(txt);
    }
  }
});
