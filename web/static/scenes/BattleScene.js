/**
 * BattleScene - Main battle rendering scene.
 * Renders Boss, characters, skill animations, and damage numbers.
 */
var BattleScene = new Phaser.Class({
  Extends: Phaser.Scene,

  initialize: function BattleScene() {
    Phaser.Scene.call(this, { key: 'BattleScene' });
    this._entities = {};   // id -> sprite
    this._hpBars = {};     // id -> { bg, fill }
    this._nameTexts = {};  // id -> text
    this._lastState = null;
    this._animQueue = [];
    this._animPlaying = false;
  },

  create: function () {
    // Battlefield background
    this._drawBattleground();

    // Container groups
    this.entityGroup = this.add.group();
    this.fxGroup = this.add.group();
    this.textGroup = this.add.group();

    // Listen for WebSocket events
    var self = this;
    GameWS.on('state_update', function (data) { self._onStateUpdate(data); });
    GameWS.on('animation', function (data) { self._onAnimation(data); });
    GameWS.on('game_over', function (data) { self._onGameOver(data); });

    // Connect WebSocket after scene is ready
    GameWS.connect();

    // Launch UI overlay scene
    this.scene.launch('UIScene');
  },

  /* ===== Battleground background ===== */
  _drawBattleground: function () {
    var g = this.add.graphics();

    // Dark floor gradient
    g.fillStyle(0x0a0a1a, 1);
    g.fillRect(0, 0, 960, 640);

    // Stone floor tiles
    for (var y = 0; y < 640; y += 32) {
      for (var x = 0; x < 960; x += 32) {
        var shade = 0x111122 + ((x + y) % 64 === 0 ? 0x050508 : 0);
        g.fillStyle(shade, 1);
        g.fillRect(x, y, 31, 31);
      }
    }

    // Arena circle (subtle)
    g.lineStyle(2, 0x222244, 0.4);
    g.strokeCircle(480, 340, 260);
    g.lineStyle(1, 0x222244, 0.2);
    g.strokeCircle(480, 340, 200);

    // Top border glow (boss area)
    g.fillStyle(0x330000, 0.3);
    g.fillRect(0, 0, 960, 80);
  },

  /* ===== State Update Handler ===== */
  _onStateUpdate: function (data) {
    if (!data) return;
    this._lastState = data;

    // Update boss
    if (data.boss) {
      this._updateEntity('boss', data.boss, true);
    }

    // Update characters (dict: {id: charData})
    if (data.characters) {
      var chars = data.characters;
      var charKeys = Object.keys(chars);
      for (var i = 0; i < charKeys.length; i++) {
        var cid = charKeys[i];
        this._updateEntity(cid, chars[cid], false);
      }
    }

    // Update adds (from boss.adds or top-level adds)
    var adds = (data.boss && data.boss.adds) || data.adds || [];
    for (var j = 0; j < adds.length; j++) {
      if (adds[j].alive) {
        this._updateEntity(adds[j].id, adds[j], false);
      }
    }

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
      this._entities[id] = sprite;
      this.entityGroup.add(sprite);

      // Name label
      var nameText = this.add.text(pos.x, pos.y + (isBoss ? 50 : 28), info.name || id, {
        fontFamily: '"Press Start 2P"',
        fontSize: '8px',
        color: isBoss ? '#ff4444' : '#ccccdd',
        align: 'center'
      }).setOrigin(0.5, 0);
      this._nameTexts[id] = nameText;
      this.textGroup.add(nameText);
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
          y: pos.y + (isBoss ? 50 : 28),
          duration: 300,
          ease: 'Power2'
        });
      }
    }

    // Death state
    if (info.hp !== undefined && info.hp <= 0 && info.alive === false) {
      sprite.setTint(0x444444);
      sprite.setAlpha(0.5);
    } else {
      sprite.clearTint();
      sprite.setAlpha(1);
    }
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

  /* ===== Position calculation ===== */
  _getEntityPosition: function (id, info, isBoss) {
    if (isBoss) {
      return { x: 480, y: 120 };
    }

    // Characters arranged in a semicircle at bottom
    var charPositions = {
      tank: { x: 480, y: 460 },
      healer: { x: 320, y: 480 },
      mage: { x: 640, y: 480 },
      rogue: { x: 380, y: 520 },
      hunter: { x: 580, y: 520 }
    };

    var role = info.role || info.type;
    if (charPositions[role]) {
      return charPositions[role];
    }

    // Minions around boss
    if (role === 'minion') {
      var idx = parseInt(id.replace(/\D/g, ''), 10) || 0;
      return {
        x: 300 + (idx % 4) * 120,
        y: 200 + Math.floor(idx / 4) * 60
      };
    }

    return { x: 480, y: 400 };
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
    var count = 20;
    var completed = 0;

    for (var i = 0; i < count; i++) {
      var x = 200 + Math.random() * 560;
      var delay = Math.random() * 600;
      var ice = this.add.sprite(x, -10, 'fx_ice');
      ice.setScale(1.5);
      ice.setAlpha(0.8);
      this.fxGroup.add(ice);

      this.tweens.add({
        targets: ice,
        y: 500 + Math.random() * 100,
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

    // Dash to target
    this.tweens.add({
      targets: src,
      x: to.x + 20,
      y: to.y,
      duration: 100,
      ease: 'Power3',
      onComplete: function () {
        // Slash effect
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

        // Return to position
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

    var phaseText = this.add.text(480, 300, 'PHASE ' + (anim.phase || '?'), {
      fontFamily: '"Press Start 2P"',
      fontSize: '28px',
      color: '#ffcc00',
      stroke: '#000000',
      strokeThickness: 4
    }).setOrigin(0.5);
    this.textGroup.add(phaseText);

    this.tweens.add({
      targets: phaseText,
      y: 260,
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

  /* ===== Death animation ===== */
  _animDeath: function (anim, done) {
    var sprite = this._entities[anim.target_id];
    if (!sprite) { done(); return; }

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
        onComplete: function () {
          p.destroy();
          completed++;
          if (completed >= 5) {
            if (anim.value) this._showDamageNumber(anim.target_id, anim.value, false);
            done();
          }
        }.bind(this)
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
      strokeThickness: 3
    }).setOrigin(0.5);
    this.textGroup.add(dmgText);

    this.tweens.add({
      targets: dmgText,
      y: pos.y - 60,
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
    var self = this;
    this.time.delayedCall(120, function () {
      if (sprite.active) sprite.clearTint();
    });
  },

  /* ===== Get entity position helper ===== */
  _getEntityPos: function (entityId) {
    var sprite = this._entities[entityId];
    if (sprite) return { x: sprite.x, y: sprite.y };

    // Fallback: check last state for position info
    if (this._lastState) {
      if (entityId === 'boss' && this._lastState.boss) {
        return { x: 480, y: 120 };
      }
      if (this._lastState.characters) {
        var chars = this._lastState.characters;
        if (chars[entityId]) {
          return this._getEntityPosition(entityId, chars[entityId], false);
        }
        // Check all characters by id field
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

    // Darken screen
    var overlay = this.add.rectangle(480, 320, 960, 640, 0x000000, 0.6);
    overlay.setDepth(100);

    var resultText = this.add.text(480, 280, result, {
      fontFamily: '"Press Start 2P"',
      fontSize: '36px',
      color: color,
      stroke: '#000000',
      strokeThickness: 6
    }).setOrigin(0.5).setDepth(101);

    var subText = this.add.text(480, 340, data && data.message ? data.message : '', {
      fontFamily: '"Press Start 2P"',
      fontSize: '12px',
      color: '#ccccdd',
      stroke: '#000000',
      strokeThickness: 2,
      wordWrap: { width: 600 }
    }).setOrigin(0.5).setDepth(101);

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
