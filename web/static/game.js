/**
 * game.js - Phaser 3 game configuration and entry point.
 * Pixel art mode enabled, 960x640 canvas.
 */
(function () {
  'use strict';

  var config = {
    type: Phaser.CANVAS,
    width: 960,
    height: 640,
    parent: 'game-container',
    backgroundColor: '#050510',
    pixelArt: true,
    roundPixels: true,
    antialias: false,
    render: {
      pixelArt: true,
      antialias: false,
      roundPixels: true
    },
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH
    },
    scene: [BootScene, BattleScene, UIScene]
  };

  window.game = new Phaser.Game(config);
})();
