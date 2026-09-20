/* Drag-and-drop placement for "view on wall".
   Keeps the three percentage inputs in sync so they never have to be typed by hand. */
(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    var picker = document.querySelector('.wall-picker');
    if (!picker) return;

    var stage = picker.querySelector('[data-wall-stage]');
    var art = picker.querySelector('[data-wall-art]');
    var handle = picker.querySelector('[data-wall-handle]');
    var readout = picker.querySelector('[data-wall-readout]');
    var widthInput = document.getElementById('id_wall_width');
    var leftInput = document.getElementById('id_wall_left');
    var topInput = document.getElementById('id_wall_top');
    var roomInput = document.getElementById('id_wall_view');
    if (!stage || !art || !widthInput || !leftInput || !topInput) return;

    var clamp = function (n, lo, hi) { return Math.min(hi, Math.max(lo, n)); };
    var read = function (input, fallback) {
      var value = parseFloat(input.value);
      return isNaN(value) ? fallback : value;
    };

    function draw() {
      var w = clamp(read(widthInput, 24), 1, 100);
      var left = clamp(read(leftInput, 32), 0, 100);
      var top = clamp(read(topInput, 27), 0, 100);
      art.style.width = w + '%';
      art.style.left = left + '%';
      art.style.top = top + '%';
      if (readout) readout.textContent = 'width ' + w.toFixed(1) + '% of the wall';
    }

    function write(w, left, top) {
      [[widthInput, w], [leftInput, left], [topInput, top]].forEach(function (pair) {
        if (pair[1] === null) return;
        pair[0].value = pair[1].toFixed(2);
        pair[0].dispatchEvent(new Event('input', { bubbles: true }));
        pair[0].dispatchEvent(new Event('change', { bubbles: true }));
      });
      draw();
    }

    function showRoom() {
      var room = roomInput ? roomInput.value : 'large';
      picker.classList.toggle('is-off', !room);
      stage.style.backgroundImage =
        'url("' + (room === 'small' ? picker.dataset.small : picker.dataset.large) + '")';
    }

    // dragging the artwork, and dragging its corner handle
    var drag = null;

    function onDown(event, mode) {
      event.preventDefault();
      var box = stage.getBoundingClientRect();
      drag = {
        mode: mode, box: box,
        startX: event.clientX, startY: event.clientY,
        left: read(leftInput, 32), top: read(topInput, 27), width: read(widthInput, 24)
      };
      if (event.pointerId !== undefined) {
        drag.target = event.currentTarget;
        drag.target.setPointerCapture(event.pointerId);
      }
      picker.classList.add('is-dragging');
    }

    function onMove(event) {
      if (!drag) return;
      event.preventDefault();
      var dx = (event.clientX - drag.startX) / drag.box.width * 100;
      var dy = (event.clientY - drag.startY) / drag.box.height * 100;
      if (drag.mode === 'move') {
        write(null, clamp(drag.left + dx, 0, 100 - read(widthInput, 24)), clamp(drag.top + dy, 0, 98));
      } else {
        write(clamp(drag.width + dx, 2, 100 - read(leftInput, 32)), null, null);
      }
    }

    function onUp(event) {
      if (!drag) return;
      if (drag.target && event.pointerId !== undefined && drag.target.hasPointerCapture(event.pointerId)) {
        drag.target.releasePointerCapture(event.pointerId);
      }
      drag = null;
      picker.classList.remove('is-dragging');
    }

    art.addEventListener('pointerdown', function (e) {
      if (e.target === handle) return;
      onDown(e, 'move');
    });
    if (handle) handle.addEventListener('pointerdown', function (e) { onDown(e, 'resize'); });
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
    document.addEventListener('pointercancel', onUp);

    picker.querySelectorAll('[data-wall-action]').forEach(function (button) {
      button.addEventListener('click', function () {
        var action = button.dataset.wallAction;
        var w = read(widthInput, 24);
        if (action === 'bigger') write(clamp(w * 1.1, 2, 100 - read(leftInput, 32)), null, null);
        if (action === 'smaller') write(clamp(w / 1.1, 2, 100), null, null);
        if (action === 'center') write(null, clamp((100 - w) / 2, 0, 100), read(topInput, 27));
      });
    });

    [widthInput, leftInput, topInput].forEach(function (input) {
      input.addEventListener('change', draw);
    });
    if (roomInput) roomInput.addEventListener('change', showRoom);

    showRoom();
    draw();
  });
})();
