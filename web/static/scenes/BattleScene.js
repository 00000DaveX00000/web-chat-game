/**
 * BattleScene - Main battle rendering scene.
 * Renders Boss, characters, skill animations, damage numbers.
 * V5: HP bars above sprites, aggro line, AI decision bubbles, cast ring, death enhancement.
 */
var BattleScene = new Phaser.Class({
  Extends: Phaser.Scene,

  initialize: function BattleScene() {
    Phaser.Scene.call(this, { key: 'BattleScene' });
    this._entities = {};   // id -> sprite
    this._hpBars = {};     // id -> { bg, fill, isBoss }
    this._nameTexts = {};  // id -> text
    this._lastState = null;
    this._animQueue = [];
    this._animPlaying = false;
    this._aggroLine = null;
    this._castArc = null;
    this._aiBubbles = {};  // id -> text object
    this._castTexts = {};  // id -> cast text object
    this._gameOverOverlays = []; // track game over elements for reset
    // Canvas dimensions
    this.W = 720;
    this.H = 420;
    // Target name mapping for AI bubbles
    this._targetNames = {
      boss: 'Boss', tank: '坦克', healer: '治疗',
      mage: '法师', rogue: '盗贼', hunter: '猎人'
    };
  },

  create: function () {
    // Battlefield background
    this._drawBattleground();

    // Container groups (draw order matters)
    this.bgGroup = this.add.group();       // aggro line etc.
    this.entityGroup = this.add.group();
    this.barGroup = this.add.group();       // HP bars
    this.fxGroup = this.add.group();
    this.textGroup = this.add.group();

    // Aggro line graphics object
    this._aggroGfx = this.add.graphics();
    this._aggroGfx.setDepth(1);

    // Cast arc graphics object
    this._castGfx = this.add.graphics();
    this._castGfx.setDepth(5);

    // Listen for WebSocket events
    var self = this;
    GameWS.on('state_update', function (data) { self._onStateUpdate(data); });
    GameWS.on('animation', function (data) { self._onAnimation(data); });
    GameWS.on('game_over', function (data) { self._onGameOver(data); });
    GameWS.on('game_reset', function () { self._onGameReset(); });

    // Connect WebSocket after scene is ready
    GameWS.connect();

    // Launch UI overlay scene
    this.scene.launch('UIScene');
  },

  /* ===== Battleground background ===== */
  _drawBattleground: function () {
    var g = this.add.graphics();
    var W = this.W, H = this.H;

    g.fillStyle(0x0a0a1a, 1);
    g.fillRect(0, 0, W, H);

    for (var y = 0; y < H; y += 32) {
      for (var x = 0; x < W; x += 32) {
        var shade = 0x111122 + ((x + y) % 64 === 0 ? 0x050508 : 0);
        g.fillStyle(shade, 1);
        g.fillRect(x, y, 31, 31);
      }
    }

    // Center arena circle
    var cx = W / 2, cy = H / 2;
    g.lineStyle(2, 0x222244, 0.4);
    g.strokeCircle(cx, cy, 190);
    g.lineStyle(1, 0x222244, 0.2);
    g.strokeCircle(cx, cy, 150);

    // Boss side tint (left)
    g.fillStyle(0x330000, 0.2);
    g.fillRect(0, 0, W * 0.35, H);

    // Dividing line
    g.lineStyle(1, 0x333355, 0.3);
    g.beginPath();
    g.moveTo(W * 0.42, 20);
    g.lineTo(W * 0.42, H - 20);
    g.strokePath();
  },

  /* ===== State Update Handler ===== */
  _onStateUpdate: function (data) {
    if (!data) return;
    this._lastState = data;

    // Update boss
    if (data.boss) {
      this._updateEntity('boss', data.boss, true);
    }

    // Update characters
    if (data.characters) {
      var chars = data.characters;
      var charKeys = Object.keys(chars);
      for (var i = 0; i < charKeys.length; i++) {
        var cid = charKeys[i];
        this._updateEntity(cid, chars[cid], false);
      }
    }

    // Update adds + cleanup dead adds
    var adds = (data.boss && data.boss.adds) || data.adds || [];
    var aliveAddIds = {};
    for (var j = 0; j < adds.length; j++) {
      if (adds[j].alive) {
        this._updateEntity(adds[j].id, adds[j], false);
        aliveAddIds[adds[j].id] = true;
      }
    }
    // Remove sprites for dead adds
    var entityIds = Object.keys(this._entities);
    for (var k = 0; k < entityIds.length; k++) {
      var eid = entityIds[k];
      if (eid.indexOf('add_') === 0 && !aliveAddIds[eid]) {
        if (this._entities[eid]) { this._entities[eid].destroy(); delete this._entities[eid]; }
        if (this._nameTexts[eid]) { this._nameTexts[eid].destroy(); delete this._nameTexts[eid]; }
        if (this._hpBars[eid]) {
          if (this._hpBars[eid].bg) this._hpBars[eid].bg.destroy();
          if (this._hpBars[eid].fill) this._hpBars[eid].fill.destroy();
          delete this._hpBars[eid];
        }
      }
    }

    // Update aggro line (Boss -> current threat target)
    this._updateAggroLine(data);

    // Update Boss cast arc
    this._updateCastArc(data);

    // Update cast text for all entities
    this._updateAllCastTexts(data);

    // Show AI decision bubbles (actual skill text)
    this._updateAiBubbles(data);

    // Emit Phaser event for UIScene
    this.events.emit('state_changed', data);
    this.scene.get('UIScene').events.emit('state_changed', data);
  },

  /* ===== Update or create entity sprite ===== */
  _updateEntity: function (id, info, isBoss) {
    var sprite = this._entities[id];
    var textureKey = this._getTextureKey(info.role || info.type, isBoss);
    var pos = this._getEntityPosition(id, info, isBoss);

    if (!sprite) {
      sprite = this.add.sprite(pos.x, pos.y, textureKey);
      sprite.setScale(isBoss ? 2 : 1.5);
      sprite.setDepth(3);
      this._entities[id] = sprite;
      this.entityGroup.add(sprite);

      // Name label
      var nameText = this.add.text(pos.x, pos.y + (isBoss ? 50 : 30), info.name || id, {
        fontSize: '12px',
        color: isBoss ? '#ff6644' : '#eeeeff',
        stroke: '#000000',
        strokeThickness: 3,
        align: 'center'
      }).setOrigin(0.5, 0).setDepth(4);
      this._nameTexts[id] = nameText;
      this.textGroup.add(nameText);

      // Create HP bar above sprite
      this._createHpBar(id, pos, isBoss);
    }

    // Update position smoothly
    if (Math.abs(sprite.x - pos.x) > 2 || Math.abs(sprite.y - pos.y) > 2) {
      this.tweens.add({
        targets: sprite,
        x: pos.x,
        y: pos.y,
        duration: 300,
        ease: 'Power2'
      });
      var nt = this._nameTexts[id];
      if (nt) {
        this.tweens.add({
          targets: nt,
          x: pos.x,
          y: pos.y + (isBoss ? 50 : 30),
          duration: 300,
          ease: 'Power2'
        });
      }
      // Move HP bar
      this._moveHpBar(id, pos, isBoss);
    }

    // Update HP bar fill
    this._updateHpBar(id, info, isBoss);

    // Death state
    if (info.hp !== undefined && info.hp <= 0 && info.alive === false) {
      sprite.setTint(0x444444);
      sprite.setAlpha(0.5);
    } else {
      sprite.clearTint();
      sprite.setAlpha(1);
    }
  },

  /* ===== HP Bar (above sprites) ===== */
  _createHpBar: function (id, pos, isBoss) {
    var barW = isBoss ? 60 : 36;
    var barH = isBoss ? 6 : 4;
    var offsetY = isBoss ? -45 : -25;

    var bg = this.add.rectangle(pos.x, pos.y + offsetY, barW, barH, 0x222222);
    bg.setStrokeStyle(1, isBoss ? 0x663333 : 0x334433);
    bg.setOrigin(0.5, 0.5);
    bg.setDepth(6);
    this.barGroup.add(bg);

    var fillColor = isBoss ? 0xcc2222 : 0x33cc33;
    var fill = this.add.rectangle(pos.x - barW / 2, pos.y + offsetY, barW, barH - 2, fillColor);
    fill.setOrigin(0, 0.5);
    fill.setDepth(7);
    this.barGroup.add(fill);

    this._hpBars[id] = { bg: bg, fill: fill, isBoss: isBoss, barW: barW, barH: barH, offsetY: offsetY };
  },

  _moveHpBar: function (id, pos, isBoss) {
    var hb = this._hpBars[id];
    if (!hb) return;
    var offsetY = hb.offsetY;
    this.tweens.add({
      targets: hb.bg,
      x: pos.x,
      y: pos.y + offsetY,
      duration: 300,
      ease: 'Power2'
    });
    this.tweens.add({
      targets: hb.fill,
      x: pos.x - hb.barW / 2,
      y: pos.y + offsetY,
      duration: 300,
      ease: 'Power2'
    });
  },

  _updateHpBar: function (id, info, isBoss) {
    var hb = this._hpBars[id];
    if (!hb) return;
    var maxHp = info.max_hp || 1;
    var hp = info.hp || 0;
    var pct = Math.max(0, Math.min(1, hp / maxHp));
    var newW = Math.max(0, hb.barW * pct);
    hb.fill.width = newW;

    // Color change for player HP bars
    if (!isBoss) {
      if (pct > 0.6) {
        hb.fill.setFillStyle(0x33cc33);
      } else if (pct > 0.3) {
        hb.fill.setFillStyle(0xcccc33);
      } else {
        hb.fill.setFillStyle(0xcc3333);
      }
    }

    // Hide if dead
    if (hp <= 0) {
      hb.bg.setAlpha(0.3);
      hb.fill.setAlpha(0.3);
    } else {
      hb.bg.setAlpha(1);
      hb.fill.setAlpha(1);
    }
  },

  /* ===== Aggro Line (Boss -> threat target) ===== */
  _updateAggroLine: function (data) {
    this._aggroGfx.clear();
    if (!data.boss || !data.boss.current_target) return;
    var bossPos = this._getEntityPos('boss');
    var targetId = data.boss.current_target;
    var targetPos = this._getEntityPos(targetId);
    if (!bossPos || !targetPos) return;

    // Red dashed line
    this._aggroGfx.lineStyle(2, 0xff3333, 0.4);
    var dx = targetPos.x - bossPos.x;
    var dy = targetPos.y - bossPos.y;
    var dist = Math.sqrt(dx * dx + dy * dy);
    var dashLen = 8;
    var gapLen = 6;
    var steps = Math.floor(dist / (dashLen + gapLen));
    for (var i = 0; i < steps; i++) {
      var t0 = i * (dashLen + gapLen) / dist;
      var t1 = (i * (dashLen + gapLen) + dashLen) / dist;
      if (t1 > 1) t1 = 1;
      this._aggroGfx.beginPath();
      this._aggroGfx.moveTo(bossPos.x + dx * t0, bossPos.y + dy * t0);
      this._aggroGfx.lineTo(bossPos.x + dx * t1, bossPos.y + dy * t1);
      this._aggroGfx.strokePath();
    }
  },

  /* ===== Boss Cast Arc (progress ring around boss) ===== */
  _updateCastArc: function (data) {
    this._castGfx.clear();
    if (!data.boss_card || !data.boss_card.casting) return;
    var bossPos = this._getEntityPos('boss');
    if (!bossPos) return;

    var casting = data.boss_card.casting;
    var totalCast = casting.skill_name === '灭世之炎' ? 10.0 : 2.0;
    var progress = Math.max(0, 1 - casting.remaining / totalCast);
    var radius = 40;
    var startAngle = -Math.PI / 2;
    var endAngle = startAngle + (Math.PI * 2 * progress);

    this._castGfx.lineStyle(3, 0xff3333, 0.8);
    this._castGfx.beginPath();
    this._castGfx.arc(bossPos.x, bossPos.y, radius, startAngle, endAngle, false);
    this._castGfx.strokePath();

    // Outer glow ring (faint)
    this._castGfx.lineStyle(1, 0xff6644, 0.3);
    this._castGfx.beginPath();
    this._castGfx.arc(bossPos.x, bossPos.y, radius + 3, startAngle, endAngle, false);
    this._castGfx.strokePath();
  },

  /* ===== Game Reset Handler ===== */
  _onGameReset: function () {
    // Destroy game over overlays
    for (var i = 0; i < this._gameOverOverlays.length; i++) {
      if (this._gameOverOverlays[i] && this._gameOverOverlays[i].destroy) {
        this._gameOverOverlays[i].destroy();
      }
    }
    this._gameOverOverlays = [];

    // Clear all entities, HP bars, name texts
    var entityIds = Object.keys(this._entities);
    for (var i = 0; i < entityIds.length; i++) {
      var eid = entityIds[i];
      if (this._entities[eid]) this._entities[eid].destroy();
      if (this._nameTexts[eid]) this._nameTexts[eid].destroy();
      if (this._hpBars[eid]) {
        if (this._hpBars[eid].bg) this._hpBars[eid].bg.destroy();
        if (this._hpBars[eid].fill) this._hpBars[eid].fill.destroy();
      }
    }
    this._entities = {};
    this._nameTexts = {};
    this._hpBars = {};

    // Clear graphics
    this._aggroGfx.clear();
    this._castGfx.clear();

    // Clear AI bubbles
    var bubbleIds = Object.keys(this._aiBubbles);
    for (var i = 0; i < bubbleIds.length; i++) {
      if (this._aiBubbles[bubbleIds[i]]) this._aiBubbles[bubbleIds[i]].destroy();
    }
    this._aiBubbles = {};

    // Clear cast texts
    var castIds = Object.keys(this._castTexts);
    for (var i = 0; i < castIds.length; i++) {
      if (this._castTexts[castIds[i]]) this._castTexts[castIds[i]].destroy();
    }
    this._castTexts = {};

    // Clear animation queue
    this._animQueue = [];
    this._animPlaying = false;
    this._lastState = null;
  },

  /* ===== Cast Text for All Entities ===== */
  _updateAllCastTexts: function (data) {
    // Boss cast text
    if (data.boss_card && data.boss_card.casting) {
      var cast = data.boss_card.casting;
      this._showCastText('boss', cast.skill_name, cast.remaining, true);
    } else {
      this._hideCastText('boss');
    }

    // Player cast texts
    if (data.characters) {
      var roles = Object.keys(data.characters);
      for (var i = 0; i < roles.length; i++) {
        var c = data.characters[roles[i]];
        if (c.casting) {
          this._showCastText(roles[i], c.casting.skill_name, c.casting.remaining, false);
        } else {
          this._hideCastText(roles[i]);
        }
      }
    }
  },

  _showCastText: function (entityId, skillName, remaining, isBoss) {
    var pos = this._getEntityPos(entityId);
    if (!pos) return;
    var yOff = isBoss ? -60 : -42;

    var label = '⏳ ' + skillName + ' ' + remaining.toFixed(1) + 's';

    if (this._castTexts[entityId]) {
      this._castTexts[entityId].setText(label);
      this._castTexts[entityId].setPosition(pos.x, pos.y + yOff);
      return;
    }

    var txt = this.add.text(pos.x, pos.y + yOff, label, {
      fontSize: isBoss ? '14px' : '11px',
      color: isBoss ? '#ffaa44' : '#88ccff',
      backgroundColor: 'rgba(0,0,0,0.85)',
      padding: { x: 6, y: 3 },
      stroke: '#000000',
      strokeThickness: 2
    }).setOrigin(0.5).setDepth(11);
    this.textGroup.add(txt);
    this._castTexts[entityId] = txt;
  },

  _hideCastText: function (entityId) {
    if (this._castTexts[entityId]) {
      this._castTexts[entityId].destroy();
      delete this._castTexts[entityId];
    }
  },

  /* ===== AI Decision Bubbles (shows actual skill text) ===== */
  _updateAiBubbles: function (data) {
    if (!data.ai_log) return;
    var now = Date.now() / 1000;

    for (var i = 0; i < data.ai_log.length; i++) {
      var entry = data.ai_log[i];
      if (!entry.last_response || !entry.last_response.time) continue;
      var timeSince = now - entry.last_response.time;
      // Only show bubble for recent decisions (< 3 seconds)
      if (timeSince > 3) continue;

      var entityId = entry.is_boss ? 'boss' : (entry.role || '');
      if (!entityId || this._aiBubbles[entityId]) continue;

      var pos = this._getEntityPos(entityId);
      if (!pos) continue;

      // Build display text from AI response (use skill_name, not tool_name)
      var resp = entry.last_response;
      var displayText = '';
      var skillDisplay = resp.skill_name || resp.tool_name || '';
      if (skillDisplay) {
        displayText = skillDisplay;
        if (resp.target) displayText += '→' + (this._targetNames[resp.target] || resp.target);
      }

      this._showAiBubble(entityId, pos, entry.is_boss, displayText);
    }
  },

  _showAiBubble: function (entityId, pos, isBoss, displayText) {
    var bubbleText = displayText || '\u{1F4AD}';
    var yOff = isBoss ? -75 : -55;

    var bubble = this.add.text(pos.x, pos.y + yOff, bubbleText, {
      fontSize: isBoss ? '13px' : '11px',
      color: isBoss ? '#ffdd44' : '#bbeeFF',
      backgroundColor: 'rgba(0,0,0,0.85)',
      padding: { x: 6, y: 3 },
      stroke: '#000000',
      strokeThickness: 2
    }).setOrigin(0.5).setAlpha(0).setDepth(12);
    this.textGroup.add(bubble);

    var self = this;
    this._aiBubbles[entityId] = bubble;

    this.tweens.add({
      targets: bubble,
      alpha: 1,
      y: bubble.y - 10,
      duration: 250,
      ease: 'Power2',
      yoyo: true,
      hold: 2000,
      onComplete: function () {
        bubble.destroy();
        delete self._aiBubbles[entityId];
      }
    });
  },

  _getTextureKey: function (role, isBoss) {
    if (isBoss) return 'boss';
    var map = {
      tank: 'tank',
      healer: 'healer',
      mage: 'mage',
      rogue: 'rogue',
      hunter: 'hunter',
      minion: 'minion'
    };
    return map[role] || 'minion';
  },

  /* ===== Position calculation (720x420) - Left/Right layout ===== */
  _getEntityPosition: function (id, info, isBoss) {
    // Boss on LEFT side (center)
    if (isBoss) {
      return { x: 140, y: 210 };
    }

    // Players on RIGHT side: tank in front, others in back
    var charPositions = {
      tank:   { x: 400, y: 210 },  // front, closest to boss
      healer: { x: 530, y: 110 },  // back top
      mage:   { x: 620, y: 180 },  // back right
      rogue:  { x: 530, y: 310 },  // back bottom
      hunter: { x: 620, y: 260 }   // back right-bottom
    };

    var role = info.role || info.type;
    if (charPositions[role]) {
      return charPositions[role];
    }

    // Adds (熔岩元素): independent positions around the Boss
    if (id.indexOf('add_') === 0) {
      var idx = parseInt(id.replace(/\D/g, ''), 10) || 0;
      // Arrange adds in a semicircle around the boss
      var addPositions = [
        { x: 60,  y: 120 },  // top-left
        { x: 200, y: 100 },  // top-right
        { x: 60,  y: 300 },  // bottom-left
        { x: 200, y: 320 },  // bottom-right
        { x: 40,  y: 210 },  // far-left center
        { x: 230, y: 210 },  // right of boss
      ];
      if (idx < addPositions.length) {
        return addPositions[idx];
      }
      // Fallback for extra adds
      return {
        x: 60 + (idx % 3) * 80,
        y: 100 + Math.floor(idx / 3) * 110
      };
    }

    return { x: 400, y: 210 };
  },

  /* ===== Animation Handler ===== */
  _onAnimation: function (data) {
    if (!data || !data.anim_type) return;
    this._animQueue.push(data);
    this._processAnimQueue();
  },

  _processAnimQueue: function () {
    if (this._animPlaying || this._animQueue.length === 0) return;
    this._animPlaying = true;
    var anim = this._animQueue.shift();
    var self = this;
    var done = function () {
      self._animPlaying = false;
      self._processAnimQueue();
    };

    switch (anim.anim_type) {
      case 'fireball':
        this._animFireball(anim, done);
        break;
      case 'heal':
        this._animHeal(anim, done);
        break;
      case 'blizzard':
        this._animBlizzard(anim, done);
        break;
      case 'backstab':
        this._animBackstab(anim, done);
        break;
      case 'taunt':
        this._animTaunt(anim, done);
        break;
      case 'boss_attack':
        this._animBossAttack(anim, done);
        break;
      case 'arrow':
        this._animArrow(anim, done);
        break;
      case 'damage':
        this._showDamageNumber(anim.target_id, anim.value, false);
        done();
        break;
      case 'heal_number':
        this._showDamageNumber(anim.target_id, anim.value, true);
        done();
        break;
      case 'phase_change':
        this._animPhaseChange(anim, done);
        break;
      case 'death':
        this._animDeath(anim, done);
        break;
      case 'poison':
        this._animPoison(anim, done);
        break;
      case 'shield':
        this._animShield(anim, done);
        break;
      default:
        done();
    }
  },

  /* ===== Fireball animation ===== */
  _animFireball: function (anim, done) {
    var from = this._getEntityPos(anim.source_id);
    var to = this._getEntityPos(anim.target_id);
    if (!from || !to) { done(); return; }

    var fb = this.add.sprite(from.x, from.y, 'fx_fireball');
    fb.setScale(2);
    this.fxGroup.add(fb);

    var self = this;
    this.tweens.add({
      targets: fb,
      x: to.x,
      y: to.y,
      duration: 400,
      ease: 'Power1',
      onComplete: function () {
        self._flashEntity(anim.target_id, 0xff6600);
        if (anim.value) self._showDamageNumber(anim.target_id, anim.value, false);
        fb.destroy();
        done();
      }
    });
  },

  /* ===== Heal animation ===== */
  _animHeal: function (anim, done) {
    var pos = this._getEntityPos(anim.target_id);
    if (!pos) { done(); return; }

    var hfx = this.add.sprite(pos.x, pos.y + 10, 'fx_heal');
    hfx.setScale(1.5);
    hfx.setAlpha(0);
    this.fxGroup.add(hfx);

    var self = this;
    this.tweens.add({
      targets: hfx,
      y: pos.y - 20,
      alpha: 0.8,
      scaleX: 2,
      scaleY: 2,
      duration: 500,
      ease: 'Power2',
      yoyo: true,
      onComplete: function () {
        if (anim.value) self._showDamageNumber(anim.target_id, anim.value, true);
        hfx.destroy();
        done();
      }
    });
  },

  /* ===== Blizzard animation ===== */
  _animBlizzard: function (anim, done) {
    var self = this;
    var count = 15;
    var completed = 0;

    for (var i = 0; i < count; i++) {
      var x = 150 + Math.random() * 420;
      var delay = Math.random() * 600;
      var ice = this.add.sprite(x, -10, 'fx_ice');
      ice.setScale(1.5);
      ice.setAlpha(0.8);
      this.fxGroup.add(ice);

      this.tweens.add({
        targets: ice,
        y: 340 + Math.random() * 60,
        alpha: 0,
        duration: 800 + Math.random() * 400,
        delay: delay,
        ease: 'Linear',
        onComplete: function () {
          ice.destroy();
          completed++;
          if (completed >= count) {
            self.cameras.main.shake(100, 0.005);
            done();
          }
        }
      });
    }
  },

  /* ===== Backstab animation ===== */
  _animBackstab: function (anim, done) {
    var src = this._entities[anim.source_id];
    var to = this._getEntityPos(anim.target_id);
    if (!src || !to) { done(); return; }

    var origX = src.x;
    var origY = src.y;
    var self = this;

    this.tweens.add({
      targets: src,
      x: to.x + 20,
      y: to.y,
      duration: 100,
      ease: 'Power3',
      onComplete: function () {
        var slash = self.add.sprite(to.x, to.y, 'fx_slash');
        slash.setScale(2);
        self.fxGroup.add(slash);

        self._flashEntity(anim.target_id, 0xffffff);
        if (anim.value) self._showDamageNumber(anim.target_id, anim.value, false);

        self.tweens.add({
          targets: slash,
          alpha: 0,
          scaleX: 3,
          scaleY: 3,
          duration: 200,
          onComplete: function () { slash.destroy(); }
        });

        self.tweens.add({
          targets: src,
          x: origX,
          y: origY,
          duration: 200,
          delay: 100,
          ease: 'Power2',
          onComplete: done
        });
      }
    });
  },

  /* ===== Taunt animation ===== */
  _animTaunt: function (anim, done) {
    var pos = this._getEntityPos(anim.source_id);
    if (!pos) { done(); return; }

    var ring = this.add.sprite(pos.x, pos.y, 'fx_taunt');
    ring.setScale(0.5);
    ring.setAlpha(1);
    this.fxGroup.add(ring);

    this.tweens.add({
      targets: ring,
      scaleX: 3,
      scaleY: 3,
      alpha: 0,
      duration: 600,
      ease: 'Power2',
      onComplete: function () {
        ring.destroy();
        done();
      }
    });
  },

  /* ===== Boss attack shockwave ===== */
  _animBossAttack: function (anim, done) {
    var from = this._getEntityPos('boss');
    var to = this._getEntityPos(anim.target_id);
    if (!from || !to) { done(); return; }

    var sw = this.add.sprite(from.x, from.y + 30, 'fx_shockwave');
    sw.setScale(2);
    this.fxGroup.add(sw);

    var self = this;
    this.tweens.add({
      targets: sw,
      x: to.x,
      y: to.y,
      scaleX: 3,
      duration: 350,
      ease: 'Power2',
      onComplete: function () {
        self._flashEntity(anim.target_id, 0xff2200);
        self.cameras.main.shake(80, 0.008);
        if (anim.value) self._showDamageNumber(anim.target_id, anim.value, false);
        sw.destroy();
        done();
      }
    });
  },

  /* ===== Arrow animation ===== */
  _animArrow: function (anim, done) {
    var from = this._getEntityPos(anim.source_id);
    var to = this._getEntityPos(anim.target_id);
    if (!from || !to) { done(); return; }

    var arrow = this.add.sprite(from.x, from.y, 'fx_arrow');
    arrow.setScale(2);
    arrow.setRotation(Phaser.Math.Angle.Between(from.x, from.y, to.x, to.y));
    this.fxGroup.add(arrow);

    var self = this;
    this.tweens.add({
      targets: arrow,
      x: to.x,
      y: to.y,
      duration: 300,
      ease: 'Linear',
      onComplete: function () {
        self._flashEntity(anim.target_id, 0xffffff);
        if (anim.value) self._showDamageNumber(anim.target_id, anim.value, false);
        arrow.destroy();
        done();
      }
    });
  },

  /* ===== Phase change effect ===== */
  _animPhaseChange: function (anim, done) {
    var self = this;
    this.cameras.main.shake(500, 0.015);
    this.cameras.main.flash(400, 255, 100, 0);

    var cx = this.W / 2;
    var phaseText = this.add.text(cx, 190, 'PHASE ' + (anim.phase || '?'), {
      fontFamily: '"Press Start 2P"',
      fontSize: '24px',
      color: '#ffcc00',
      stroke: '#000000',
      strokeThickness: 4
    }).setOrigin(0.5);
    this.textGroup.add(phaseText);

    this.tweens.add({
      targets: phaseText,
      y: 160,
      alpha: 0,
      scaleX: 1.5,
      scaleY: 1.5,
      duration: 1500,
      ease: 'Power2',
      onComplete: function () {
        phaseText.destroy();
        done();
      }
    });
  },

  /* ===== Death animation (enhanced: flash + skull + particles) ===== */
  _animDeath: function (anim, done) {
    var sprite = this._entities[anim.target_id];
    if (!sprite) { done(); return; }

    var self = this;
    var pos = { x: sprite.x, y: sprite.y };

    // Screen flash
    this.cameras.main.flash(200, 255, 255, 255, false);

    // Particle burst
    for (var i = 0; i < 8; i++) {
      var p = this.add.sprite(pos.x, pos.y, 'particle');
      p.setScale(1.5);
      p.setTint(0xff4444);
      p.setDepth(8);
      this.fxGroup.add(p);
      var angle = (Math.PI * 2 / 8) * i;
      this.tweens.add({
        targets: p,
        x: pos.x + Math.cos(angle) * 30,
        y: pos.y + Math.sin(angle) * 30,
        alpha: 0,
        duration: 500,
        ease: 'Power2',
        onComplete: (function(particle) {
          return function() { particle.destroy(); };
        })(p)
      });
    }

    // Skull icon fading out
    var skull = this.add.text(pos.x, pos.y - 20, '\u2620', {
      fontSize: '20px'
    }).setOrigin(0.5).setDepth(10);
    this.textGroup.add(skull);

    this.tweens.add({
      targets: skull,
      y: pos.y - 50,
      alpha: 0,
      duration: 1200,
      ease: 'Power2',
      onComplete: function() { skull.destroy(); }
    });

    // Entity death tilt
    sprite.setTint(0x444444);
    this.tweens.add({
      targets: sprite,
      alpha: 0.4,
      angle: 90,
      y: sprite.y + 10,
      duration: 500,
      ease: 'Power2',
      onComplete: done
    });
  },

  /* ===== Poison effect ===== */
  _animPoison: function (anim, done) {
    var pos = this._getEntityPos(anim.target_id);
    if (!pos) { done(); return; }

    var completed = 0;
    var self = this;
    for (var i = 0; i < 5; i++) {
      var p = this.add.sprite(pos.x - 8 + Math.random() * 16, pos.y + 10, 'fx_poison');
      p.setScale(1.5);
      this.fxGroup.add(p);

      this.tweens.add({
        targets: p,
        y: pos.y - 20 - Math.random() * 10,
        alpha: 0,
        duration: 500,
        delay: i * 80,
        onComplete: (function (particle, animRef) {
          return function () {
            particle.destroy();
            completed++;
            if (completed >= 5) {
              if (animRef.value) self._showDamageNumber(animRef.target_id, animRef.value, false);
              done();
            }
          };
        })(p, anim)
      });
    }
  },

  /* ===== Shield effect ===== */
  _animShield: function (anim, done) {
    var pos = this._getEntityPos(anim.source_id || anim.target_id);
    if (!pos) { done(); return; }

    var shield = this.add.sprite(pos.x, pos.y, 'fx_shield');
    shield.setScale(1.5);
    shield.setAlpha(0);
    this.fxGroup.add(shield);

    this.tweens.add({
      targets: shield,
      alpha: 0.8,
      scaleX: 2,
      scaleY: 2,
      duration: 300,
      yoyo: true,
      onComplete: function () {
        shield.destroy();
        done();
      }
    });
  },

  /* ===== Damage / Heal floating number ===== */
  _showDamageNumber: function (entityId, value, isHeal) {
    var pos = this._getEntityPos(entityId);
    if (!pos) return;

    var text = (isHeal ? '+' : '-') + Math.abs(Math.round(value));
    var color = isHeal ? '#33ff66' : '#ff3333';
    var offsetX = -20 + Math.random() * 40;

    var dmgText = this.add.text(pos.x + offsetX, pos.y - 20, text, {
      fontFamily: '"Press Start 2P"',
      fontSize: '14px',
      color: color,
      stroke: '#000000',
      strokeThickness: 4
    }).setOrigin(0.5).setDepth(10);
    this.textGroup.add(dmgText);

    this.tweens.add({
      targets: dmgText,
      y: pos.y - 50,
      alpha: 0,
      duration: 1000,
      ease: 'Power2',
      onComplete: function () { dmgText.destroy(); }
    });
  },

  /* ===== Flash entity ===== */
  _flashEntity: function (entityId, color) {
    var sprite = this._entities[entityId];
    if (!sprite) return;

    sprite.setTint(color);
    this.time.delayedCall(120, function () {
      if (sprite.active) sprite.clearTint();
    });
  },

  /* ===== Get entity position helper ===== */
  _getEntityPos: function (entityId) {
    var sprite = this._entities[entityId];
    if (sprite) return { x: sprite.x, y: sprite.y };

    if (this._lastState) {
      if (entityId === 'boss' && this._lastState.boss) {
        return { x: 140, y: 210 };
      }
      if (this._lastState.characters) {
        var chars = this._lastState.characters;
        if (chars[entityId]) {
          return this._getEntityPosition(entityId, chars[entityId], false);
        }
        var cKeys = Object.keys(chars);
        for (var i = 0; i < cKeys.length; i++) {
          var c = chars[cKeys[i]];
          if (c.id === entityId) {
            return this._getEntityPosition(entityId, c, false);
          }
        }
      }
    }
    return null;
  },

  /* ===== Game Over ===== */
  _onGameOver: function (data) {
    var result = data && data.result === 'victory' ? 'VICTORY!' : 'DEFEAT...';
    var color = data && data.result === 'victory' ? '#33ff66' : '#ff3333';
    var cx = this.W / 2;
    var cy = this.H / 2;

    var overlay = this.add.rectangle(cx, cy, this.W, this.H, 0x000000, 0.6);
    overlay.setDepth(100);

    var resultText = this.add.text(cx, cy - 30, result, {
      fontFamily: '"Press Start 2P"',
      fontSize: '28px',
      color: color,
      stroke: '#000000',
      strokeThickness: 6
    }).setOrigin(0.5).setDepth(101);

    var msgText = this.add.text(cx, cy + 20, data && data.message ? data.message : '', {
      fontFamily: '"Press Start 2P"',
      fontSize: '10px',
      color: '#ccccdd',
      stroke: '#000000',
      strokeThickness: 2,
      wordWrap: { width: 500 }
    }).setOrigin(0.5).setDepth(101);

    // Track for reset cleanup
    this._gameOverOverlays.push(overlay, resultText, msgText);

    this.tweens.add({
      targets: resultText,
      scaleX: 1.1,
      scaleY: 1.1,
      duration: 800,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut'
    });
  }
});
