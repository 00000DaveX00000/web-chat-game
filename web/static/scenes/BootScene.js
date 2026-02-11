/**
 * BootScene - Generates all pixel art textures using Canvas API.
 * No external image assets required.
 */
var BootScene = new Phaser.Class({
  Extends: Phaser.Scene,

  initialize: function BootScene() {
    Phaser.Scene.call(this, { key: 'BootScene' });
  },

  preload: function () {
    // Nothing to load - all textures are code-generated
  },

  create: function () {
    this._generateAllTextures();
    this.scene.start('BattleScene');
  },

  _generateAllTextures: function () {
    this._makeBoss();
    this._makeTank();
    this._makeHealer();
    this._makeMage();
    this._makeRogue();
    this._makeHunter();
    this._makeMinion();
    this._makeEffects();
  },

  /* ====== Helper: draw pixel array onto a texture ====== */
  _drawPixelArt: function (key, width, height, pixelData, palette) {
    var canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    var ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;

    for (var y = 0; y < pixelData.length; y++) {
      for (var x = 0; x < pixelData[y].length; x++) {
        var c = pixelData[y][x];
        if (c === 0 || c === ' ') continue; // transparent
        var color = palette[c] || '#ff00ff';
        ctx.fillStyle = color;
        ctx.fillRect(x, y, 1, 1);
      }
    }

    if (this.textures.exists(key)) this.textures.remove(key);
    this.textures.addCanvas(key, canvas);
  },

  /* ====== Boss: 64x64 Fire Demon ====== */
  _makeBoss: function () {
    var g = this.make.graphics({ add: false });
    g.clear();

    // Body - dark red
    g.fillStyle(0x881111, 1);
    g.fillRect(16, 20, 32, 30);

    // Head
    g.fillStyle(0xbb2222, 1);
    g.fillRect(20, 8, 24, 16);

    // Horns
    g.fillStyle(0x660000, 1);
    g.fillRect(16, 4, 6, 10);
    g.fillRect(42, 4, 6, 10);
    g.fillStyle(0xff4400, 1);
    g.fillRect(18, 2, 4, 4);
    g.fillRect(44, 2, 4, 4);

    // Eyes - glowing yellow
    g.fillStyle(0xffcc00, 1);
    g.fillRect(24, 12, 4, 4);
    g.fillRect(36, 12, 4, 4);

    // Pupils
    g.fillStyle(0xff0000, 1);
    g.fillRect(26, 14, 2, 2);
    g.fillRect(38, 14, 2, 2);

    // Mouth
    g.fillStyle(0xff4400, 1);
    g.fillRect(26, 20, 12, 2);
    g.fillStyle(0xffffff, 1);
    g.fillRect(28, 20, 2, 2);
    g.fillRect(32, 20, 2, 2);
    g.fillRect(36, 20, 2, 2);

    // Arms
    g.fillStyle(0x991111, 1);
    g.fillRect(8, 24, 8, 20);
    g.fillRect(48, 24, 8, 20);

    // Claws
    g.fillStyle(0xff6600, 1);
    g.fillRect(6, 42, 4, 6);
    g.fillRect(12, 44, 4, 6);
    g.fillRect(50, 42, 4, 6);
    g.fillRect(54, 44, 4, 6);

    // Legs
    g.fillStyle(0x771111, 1);
    g.fillRect(20, 50, 10, 10);
    g.fillRect(34, 50, 10, 10);

    // Fire aura particles
    g.fillStyle(0xff6600, 0.8);
    g.fillRect(12, 16, 4, 4);
    g.fillRect(48, 16, 4, 4);
    g.fillRect(8, 30, 4, 4);
    g.fillRect(52, 28, 4, 4);

    g.fillStyle(0xffaa00, 0.6);
    g.fillRect(10, 10, 3, 3);
    g.fillRect(50, 12, 3, 3);
    g.fillRect(30, 4, 4, 4);

    g.generateTexture('boss', 64, 64);
    g.destroy();
  },

  /* ====== Tank: 32x32 Silver Armored Warrior ====== */
  _makeTank: function () {
    var g = this.make.graphics({ add: false });

    // Body armor
    g.fillStyle(0xaaaacc, 1);
    g.fillRect(10, 10, 12, 14);

    // Head
    g.fillStyle(0xddddee, 1);
    g.fillRect(12, 2, 8, 8);

    // Helmet
    g.fillStyle(0x888899, 1);
    g.fillRect(10, 1, 12, 4);
    g.fillRect(11, 4, 10, 2);

    // Eye slit
    g.fillStyle(0x333344, 1);
    g.fillRect(14, 5, 4, 2);

    // Shield (left)
    g.fillStyle(0x7777aa, 1);
    g.fillRect(2, 10, 8, 12);
    g.fillStyle(0x9999cc, 1);
    g.fillRect(3, 11, 6, 10);
    g.fillStyle(0xbbbbdd, 1);
    g.fillRect(5, 14, 2, 4);

    // Sword (right)
    g.fillStyle(0xccccdd, 1);
    g.fillRect(24, 6, 2, 14);
    g.fillStyle(0x886644, 1);
    g.fillRect(22, 18, 6, 2);
    g.fillStyle(0xffcc00, 1);
    g.fillRect(24, 4, 2, 2);

    // Legs
    g.fillStyle(0x666688, 1);
    g.fillRect(12, 24, 4, 6);
    g.fillRect(18, 24, 4, 6);

    // Boots
    g.fillStyle(0x555566, 1);
    g.fillRect(11, 28, 5, 3);
    g.fillRect(17, 28, 5, 3);

    g.generateTexture('tank', 32, 32);
    g.destroy();
  },

  /* ====== Healer: 32x32 White Robed Priest ====== */
  _makeHealer: function () {
    var g = this.make.graphics({ add: false });

    // Robe
    g.fillStyle(0xeeeeff, 1);
    g.fillRect(10, 10, 12, 16);
    g.fillRect(8, 22, 16, 6);

    // Head
    g.fillStyle(0xffccaa, 1);
    g.fillRect(12, 2, 8, 8);

    // Hood
    g.fillStyle(0xddddee, 1);
    g.fillRect(11, 1, 10, 5);

    // Eyes
    g.fillStyle(0x3366ff, 1);
    g.fillRect(14, 5, 2, 2);
    g.fillRect(18, 5, 2, 2);

    // Cross emblem
    g.fillStyle(0xff3333, 1);
    g.fillRect(15, 13, 2, 6);
    g.fillRect(13, 15, 6, 2);

    // Staff
    g.fillStyle(0x886644, 1);
    g.fillRect(26, 4, 2, 22);
    g.fillStyle(0xffcc00, 1);
    g.fillRect(24, 2, 6, 4);
    g.fillStyle(0x33ff66, 1);
    g.fillRect(26, 2, 2, 2);

    // Feet
    g.fillStyle(0xccccdd, 1);
    g.fillRect(11, 27, 4, 3);
    g.fillRect(17, 27, 4, 3);

    g.generateTexture('healer', 32, 32);
    g.destroy();
  },

  /* ====== Mage: 32x32 Blue Robed Mage ====== */
  _makeMage: function () {
    var g = this.make.graphics({ add: false });

    // Robe
    g.fillStyle(0x3344aa, 1);
    g.fillRect(10, 10, 12, 16);
    g.fillRect(8, 22, 16, 6);

    // Head
    g.fillStyle(0xffccaa, 1);
    g.fillRect(12, 4, 8, 7);

    // Wizard hat
    g.fillStyle(0x2233aa, 1);
    g.fillRect(10, 3, 12, 4);
    g.fillRect(12, 0, 8, 4);
    g.fillRect(14, -1, 4, 2);

    // Hat star
    g.fillStyle(0xffcc00, 1);
    g.fillRect(15, 1, 2, 2);

    // Eyes
    g.fillStyle(0x66ccff, 1);
    g.fillRect(14, 6, 2, 2);
    g.fillRect(18, 6, 2, 2);

    // Robe trim
    g.fillStyle(0x4466cc, 1);
    g.fillRect(10, 10, 12, 2);

    // Staff
    g.fillStyle(0x664422, 1);
    g.fillRect(26, 4, 2, 22);

    // Staff crystal
    g.fillStyle(0x66ccff, 1);
    g.fillRect(24, 1, 6, 5);
    g.fillStyle(0xaaeeff, 1);
    g.fillRect(25, 2, 4, 3);
    g.fillStyle(0xffffff, 1);
    g.fillRect(26, 2, 2, 2);

    // Feet
    g.fillStyle(0x222266, 1);
    g.fillRect(11, 27, 4, 3);
    g.fillRect(17, 27, 4, 3);

    g.generateTexture('mage', 32, 32);
    g.destroy();
  },

  /* ====== Rogue: 32x32 Dark Cloaked Assassin ====== */
  _makeRogue: function () {
    var g = this.make.graphics({ add: false });

    // Cloak
    g.fillStyle(0x333344, 1);
    g.fillRect(10, 8, 12, 16);
    g.fillRect(8, 12, 16, 10);

    // Hood shadow
    g.fillStyle(0x222233, 1);
    g.fillRect(11, 2, 10, 8);
    g.fillRect(10, 4, 12, 6);

    // Face (partially hidden)
    g.fillStyle(0xddbb99, 1);
    g.fillRect(13, 5, 6, 4);

    // Eyes
    g.fillStyle(0xccff33, 1);
    g.fillRect(14, 6, 2, 1);
    g.fillRect(18, 6, 2, 1);

    // Mask
    g.fillStyle(0x222222, 1);
    g.fillRect(13, 8, 6, 2);

    // Dagger (right hand)
    g.fillStyle(0xcccccc, 1);
    g.fillRect(24, 10, 2, 10);
    g.fillStyle(0xeeeeee, 1);
    g.fillRect(24, 8, 2, 3);
    g.fillStyle(0x553322, 1);
    g.fillRect(23, 18, 4, 3);

    // Off-hand dagger (left)
    g.fillStyle(0xaaaaaa, 1);
    g.fillRect(6, 14, 2, 8);
    g.fillStyle(0x553322, 1);
    g.fillRect(5, 20, 4, 3);

    // Legs
    g.fillStyle(0x2a2a3a, 1);
    g.fillRect(12, 24, 4, 6);
    g.fillRect(18, 24, 4, 6);

    // Boots
    g.fillStyle(0x3a3a44, 1);
    g.fillRect(11, 28, 5, 3);
    g.fillRect(17, 28, 5, 3);

    g.generateTexture('rogue', 32, 32);
    g.destroy();
  },

  /* ====== Hunter: 32x32 Green Archer ====== */
  _makeHunter: function () {
    var g = this.make.graphics({ add: false });

    // Tunic
    g.fillStyle(0x338833, 1);
    g.fillRect(10, 10, 12, 12);

    // Head
    g.fillStyle(0xffccaa, 1);
    g.fillRect(12, 2, 8, 8);

    // Hood / cap
    g.fillStyle(0x226622, 1);
    g.fillRect(11, 1, 10, 4);
    g.fillRect(20, 2, 4, 3);

    // Eyes
    g.fillStyle(0x33aa33, 1);
    g.fillRect(14, 5, 2, 2);
    g.fillRect(18, 5, 2, 2);

    // Belt
    g.fillStyle(0x664422, 1);
    g.fillRect(10, 20, 12, 2);
    g.fillStyle(0xffcc00, 1);
    g.fillRect(15, 20, 2, 2);

    // Bow (left hand)
    g.fillStyle(0x885522, 1);
    g.fillRect(4, 6, 2, 20);
    g.fillRect(2, 6, 4, 2);
    g.fillRect(2, 24, 4, 2);

    // Bowstring
    g.fillStyle(0xcccccc, 1);
    g.fillRect(5, 8, 1, 16);

    // Arrow
    g.fillStyle(0xaaaaaa, 1);
    g.fillRect(6, 14, 10, 1);
    g.fillStyle(0xdddddd, 1);
    g.fillRect(5, 13, 2, 3);

    // Quiver on back
    g.fillStyle(0x664422, 1);
    g.fillRect(22, 8, 4, 14);
    g.fillStyle(0xaaaaaa, 1);
    g.fillRect(23, 5, 1, 4);
    g.fillRect(25, 6, 1, 4);

    // Legs
    g.fillStyle(0x446644, 1);
    g.fillRect(12, 22, 4, 6);
    g.fillRect(18, 22, 4, 6);

    // Boots
    g.fillStyle(0x553311, 1);
    g.fillRect(11, 27, 5, 3);
    g.fillRect(17, 27, 5, 3);

    g.generateTexture('hunter', 32, 32);
    g.destroy();
  },

  /* ====== Minion: 32x32 Orange Lava Elemental ====== */
  _makeMinion: function () {
    var g = this.make.graphics({ add: false });

    // Core body
    g.fillStyle(0xff6600, 1);
    g.fillRect(8, 8, 16, 16);

    // Inner glow
    g.fillStyle(0xffaa33, 1);
    g.fillRect(10, 10, 12, 12);

    // Hot center
    g.fillStyle(0xffcc66, 1);
    g.fillRect(12, 12, 8, 8);

    // Eyes
    g.fillStyle(0xff0000, 1);
    g.fillRect(12, 12, 3, 3);
    g.fillRect(18, 12, 3, 3);

    // Pupils
    g.fillStyle(0xffff00, 1);
    g.fillRect(13, 13, 1, 1);
    g.fillRect(19, 13, 1, 1);

    // Mouth
    g.fillStyle(0xff2200, 1);
    g.fillRect(14, 18, 6, 2);

    // Flame top
    g.fillStyle(0xff4400, 0.9);
    g.fillRect(12, 4, 4, 6);
    g.fillRect(18, 5, 4, 5);
    g.fillRect(14, 2, 6, 4);

    g.fillStyle(0xffaa00, 0.7);
    g.fillRect(14, 1, 3, 3);
    g.fillRect(19, 3, 3, 3);

    // Dripping lava
    g.fillStyle(0xff4400, 0.8);
    g.fillRect(10, 24, 4, 4);
    g.fillRect(18, 24, 4, 4);
    g.fillRect(14, 26, 4, 4);

    g.generateTexture('minion', 32, 32);
    g.destroy();
  },

  /* ====== Effect textures ====== */
  _makeEffects: function () {
    var g;

    // Fireball - 16x16
    g = this.make.graphics({ add: false });
    g.fillStyle(0xff6600, 1);
    g.fillCircle(8, 8, 6);
    g.fillStyle(0xffaa00, 1);
    g.fillCircle(8, 8, 4);
    g.fillStyle(0xffdd44, 1);
    g.fillCircle(8, 8, 2);
    g.generateTexture('fx_fireball', 16, 16);
    g.destroy();

    // Ice shard - 8x8
    g = this.make.graphics({ add: false });
    g.fillStyle(0x66ccff, 1);
    g.fillRect(2, 0, 4, 8);
    g.fillRect(0, 2, 8, 4);
    g.fillStyle(0xaaeeff, 1);
    g.fillRect(3, 1, 2, 6);
    g.generateTexture('fx_ice', 8, 8);
    g.destroy();

    // Heal circle - 32x32
    g = this.make.graphics({ add: false });
    g.fillStyle(0x33ff66, 0.3);
    g.fillCircle(16, 16, 14);
    g.fillStyle(0x33ff66, 0.6);
    g.fillCircle(16, 16, 10);
    g.fillStyle(0x99ffaa, 0.4);
    g.fillCircle(16, 16, 6);
    g.generateTexture('fx_heal', 32, 32);
    g.destroy();

    // Taunt ring - 32x32
    g = this.make.graphics({ add: false });
    g.lineStyle(2, 0xffaa00, 0.8);
    g.strokeCircle(16, 16, 14);
    g.lineStyle(1, 0xffcc44, 0.5);
    g.strokeCircle(16, 16, 10);
    g.generateTexture('fx_taunt', 32, 32);
    g.destroy();

    // Boss attack shockwave - 48x16
    g = this.make.graphics({ add: false });
    g.fillStyle(0xff2200, 0.8);
    g.fillRect(0, 4, 48, 8);
    g.fillStyle(0xff6600, 0.5);
    g.fillRect(4, 2, 40, 12);
    g.fillStyle(0xffaa00, 0.3);
    g.fillRect(8, 0, 32, 16);
    g.generateTexture('fx_shockwave', 48, 16);
    g.destroy();

    // Poison drip - 8x8
    g = this.make.graphics({ add: false });
    g.fillStyle(0x33cc33, 1);
    g.fillRect(2, 0, 4, 4);
    g.fillRect(3, 4, 2, 3);
    g.fillRect(3, 6, 2, 2);
    g.generateTexture('fx_poison', 8, 8);
    g.destroy();

    // Arrow projectile - 16x4
    g = this.make.graphics({ add: false });
    g.fillStyle(0xaaaaaa, 1);
    g.fillRect(0, 1, 14, 2);
    g.fillStyle(0xcccccc, 1);
    g.fillTriangle(14, 0, 16, 2, 14, 4);
    g.fillStyle(0x885522, 1);
    g.fillRect(0, 1, 4, 2);
    g.generateTexture('fx_arrow', 16, 4);
    g.destroy();

    // Shield buff glow - 32x32
    g = this.make.graphics({ add: false });
    g.lineStyle(2, 0x6688ff, 0.6);
    g.strokeCircle(16, 16, 14);
    g.lineStyle(1, 0x88aaff, 0.3);
    g.strokeCircle(16, 16, 12);
    g.generateTexture('fx_shield', 32, 32);
    g.destroy();

    // Backstab slash - 16x16
    g = this.make.graphics({ add: false });
    g.fillStyle(0xffffff, 0.9);
    g.fillRect(2, 14, 12, 2);
    g.fillRect(4, 10, 10, 2);
    g.fillRect(6, 6, 8, 2);
    g.fillRect(8, 2, 6, 2);
    g.generateTexture('fx_slash', 16, 16);
    g.destroy();

    // Death marker (grey X) - 32x32
    g = this.make.graphics({ add: false });
    g.fillStyle(0x666666, 0.7);
    for (var i = 0; i < 28; i++) {
      g.fillRect(2 + i, 2 + i, 3, 3);
      g.fillRect(27 - i, 2 + i, 3, 3);
    }
    g.generateTexture('fx_death', 32, 32);
    g.destroy();

    // Generic particle - 4x4
    g = this.make.graphics({ add: false });
    g.fillStyle(0xffffff, 1);
    g.fillRect(0, 0, 4, 4);
    g.generateTexture('particle', 4, 4);
    g.destroy();
  }
});
