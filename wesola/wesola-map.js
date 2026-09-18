/**
 * Wesoła map pan + zoom (OSM / Google Maps–style).
 * Zooms by changing layout size (keeps SVG crisp) and pans with translate,
 * clamped so the map never reveals empty space past its edges.
 */
(function (global) {
  'use strict';

  var MIN_SCALE = 0.4;
  var MAX_SCALE = 5;
  var ZOOM_STEP = 1.35;
  var DRAG_THRESHOLD_PX = 6;

  function createMapNavigator(viewport, stage) {
    var scale = 1;
    var x = 0;
    var y = 0;
    var baseW = 0;
    var baseH = 0;

    var pointerActive = false;
    var didDrag = false;
    var pointerId = null;
    var startClientX = 0;
    var startClientY = 0;
    var originX = 0;
    var originY = 0;

    function measureBaseSize() {
      var prevTransform = stage.style.transform;
      var prevWidth = stage.style.width;
      stage.style.transform = 'translate(0px, 0px)';
      stage.style.width = '100%';
      baseW = stage.offsetWidth;
      baseH = stage.offsetHeight;
      if (!baseW || !baseH) {
        var svg = stage.querySelector('svg');
        if (svg) {
          var rect = svg.getBoundingClientRect();
          baseW = rect.width;
          baseH = rect.height;
        }
      }
      stage.style.width = prevWidth;
      stage.style.transform = prevTransform;
    }

    function contentSize() {
      return {
        w: baseW * scale,
        h: baseH * scale
      };
    }

    function applyTransform() {
      // Resize (not CSS scale) so the SVG reflows as vectors — no soft bitmap upscale.
      stage.style.width = contentSize().w + 'px';
      stage.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
      viewport.classList.toggle('is-zoomed', Math.abs(scale - 1) > 0.001);
      viewport.classList.toggle('is-panning', didDrag && pointerActive);
    }

    function clampPan() {
      var viewW = viewport.clientWidth;
      var viewH = viewport.clientHeight;
      var size = contentSize();
      var contentW = size.w;
      var contentH = size.h;

      if (contentW <= viewW) {
        x = (viewW - contentW) / 2;
      } else {
        x = Math.min(0, Math.max(viewW - contentW, x));
      }

      // Top-align when the map is smaller than the window so overview stays visible
      // under the title (vertical centering would hide it in a tall viewport).
      if (contentH <= viewH) {
        y = 0;
      } else {
        y = Math.min(0, Math.max(viewH - contentH, y));
      }
    }

    function setScaleAround(nextScale, focalX, focalY) {
      nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
      if (nextScale === scale) {
        clampPan();
        applyTransform();
        return;
      }
      var contentX = (focalX - x) / scale;
      var contentY = (focalY - y) / scale;
      scale = nextScale;
      x = focalX - contentX * scale;
      y = focalY - contentY * scale;
      clampPan();
      applyTransform();
    }

    function zoomBy(factor) {
      var cx = viewport.clientWidth / 2;
      var cy = viewport.clientHeight / 2;
      setScaleAround(scale * factor, cx, cy);
    }

    function zoomIn() {
      zoomBy(ZOOM_STEP);
    }

    function zoomOut() {
      zoomBy(1 / ZOOM_STEP);
    }

    function onPointerDown(event) {
      if (event.button !== undefined && event.button !== 0) {
        return;
      }
      if (event.target.closest && event.target.closest('.zoom-controls')) {
        return;
      }
      pointerActive = true;
      didDrag = false;
      pointerId = event.pointerId;
      startClientX = event.clientX;
      startClientY = event.clientY;
      originX = x;
      originY = y;
      // Do NOT capture yet — capturing here steals clicks from puzzle pieces.
    }

    function onPointerMove(event) {
      if (!pointerActive || event.pointerId !== pointerId) {
        return;
      }
      var dx = event.clientX - startClientX;
      var dy = event.clientY - startClientY;
      if (!didDrag && Math.hypot(dx, dy) >= DRAG_THRESHOLD_PX) {
        didDrag = true;
        viewport.classList.add('is-panning');
        try {
          viewport.setPointerCapture(event.pointerId);
        } catch (err) {
          /* ignore */
        }
      }
      if (!didDrag) {
        return;
      }
      x = originX + dx;
      y = originY + dy;
      clampPan();
      applyTransform();
      event.preventDefault();
    }

    function onPointerUp(event) {
      if (event.pointerId !== pointerId) {
        return;
      }
      pointerActive = false;
      pointerId = null;
      viewport.classList.remove('is-panning');
      try {
        if (viewport.hasPointerCapture && viewport.hasPointerCapture(event.pointerId)) {
          viewport.releasePointerCapture(event.pointerId);
        }
      } catch (err) {
        /* ignore */
      }
      // didDrag stays true until click capture sees it (or cleared below if no click).
      if (!didDrag) {
        didDrag = false;
      }
    }

    // After a real drag, swallow the following click so pieces don't toggle.
    function onClickCapture(event) {
      if (didDrag) {
        event.preventDefault();
        event.stopPropagation();
        didDrag = false;
      }
    }

    function onResize() {
      var prevScale = scale;
      measureBaseSize();
      if (baseH > 0) {
        viewport.style.height = baseH + 'px';
      }
      scale = prevScale;
      clampPan();
      applyTransform();
    }

    function init() {
      measureBaseSize();
      // Window stays at the "fit" size; zoomed-out map letterboxes inside it.
      if (baseH > 0) {
        viewport.style.height = baseH + 'px';
      }
      scale = 1;
      x = 0;
      y = 0;
      clampPan();
      applyTransform();

      viewport.addEventListener('pointerdown', onPointerDown);
      viewport.addEventListener('pointermove', onPointerMove);
      viewport.addEventListener('pointerup', onPointerUp);
      viewport.addEventListener('pointercancel', onPointerUp);
      // Capture on viewport so we see the click even if it targets a path.
      viewport.addEventListener('click', onClickCapture, true);
      window.addEventListener('resize', onResize);
    }

    init();

    return {
      zoomIn: zoomIn,
      zoomOut: zoomOut,
      refresh: onResize
    };
  }

  global.createWesolaMapNavigator = createMapNavigator;
})(window);
