/**
 * UIScene - Minimal overlay UI layer.
 * Boss HP bars and character panels are now rendered in HTML.
 * This scene only handles Phaser-specific overlays if needed.
 */
var UIScene = new Phaser.Class({
  Extends: Phaser.Scene,

  initialize: function UIScene() {
    Phaser.Scene.call(this, { key: 'UIScene' });
    this._lastState = null;
  },

  create: function () {
    // Listen for state changes from BattleScene
    var self = this;
    this.events.on('state_changed', function (data) {
      self._lastState = data;
    });
  }
});
