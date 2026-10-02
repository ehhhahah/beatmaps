/**
 * Wesoła map pan + zoom (OSM / Google Maps–style).
 * Zooms by changing layout size (keeps SVG crisp) and pans with translate,
 * clamped so the map never reveals empty space past its edges.
 *
 * At scale 1 the map stays in the resting page frame. When zoomed, the
 * viewport covers the full page and the map is scaled to cover it
 * (title / credits stay pinned on top).
 *
 * Wheel over the map zooms toward the cursor. Two-finger pinch zooms on
 * touch. At scale 1, only zoom-in is captured so the page can still scroll
 * (wheel) / so a pinch-out starts cover zoom without a pinch-in hijack.
 */
(function (global) {
  'use strict';

  var MIN_SCALE = 0.4;
  var MAX_SCALE = 5;
  var ZOOM_STEP = 1.35;
  var DRAG_THRESHOLD_PX = 6;
  // Wheel → scale: exp(-deltaY * k). Tuned for mouse notches + trackpads.
  var WHEEL_ZOOM_SENSITIVITY = 0.0018;

  function createMapNavigator(viewport, stage) {
    var shell = viewport.parentElement;
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

    // Two-finger pinch (touch events — simpler than multi-pointer bookkeeping).
    var pinchStartDistance = 0;
    var pinchStartScale = 1;
    var pinchWasExpanded = false;

    function isExpanded() {
      return Math.abs(scale - 1) > 0.001;
    }

    function measureBaseSize() {
      var prevTransform = stage.style.transform;
      var prevWidth = stage.style.width;
      var wasExpanded = viewport.classList.contains('is-expanded');

      // Always measure against the resting shell width, not the fullscreen cover.
      if (wasExpanded) {
        viewport.classList.remove('is-expanded');
      }
      viewport.style.height = '';
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
      if (wasExpanded) {
        viewport.classList.add('is-expanded');
      }
    }

    function contentSize() {
      return {
        w: baseW * scale,
        h: baseH * scale
      };
    }

    /** Minimum scale so the map covers the fullscreen viewport (object-fit: cover). */
    function coverScaleForFullscreen() {
      if (!baseW || !baseH) {
        return 1;
      }
      var viewW = window.innerWidth;
      var viewH = window.innerHeight;
      return Math.max(viewW / baseW, viewH / baseH);
    }

    function syncChrome() {
      var expanded = isExpanded();
      viewport.classList.toggle('is-zoomed', expanded);
      viewport.classList.toggle('is-expanded', expanded);
      viewport.classList.toggle('is-panning', didDrag && pointerActive);

      // Shell keeps the open-page layout height so un-zoom restores cleanly.
      if (shell && baseH > 0) {
        shell.style.height = baseH + 'px';
      }
      if (expanded) {
        viewport.style.height = '';
      } else if (baseH > 0) {
        viewport.style.height = baseH + 'px';
      }
    }

    function applyTransform() {
      // Resize (not CSS scale) so the SVG reflows as vectors — no soft bitmap upscale.
      stage.style.width = contentSize().w + 'px';
      stage.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
      syncChrome();
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

      if (contentH <= viewH) {
        // Resting frame: top-align under the title. Cover mode rarely hits this.
        y = isExpanded() ? (viewH - contentH) / 2 : 0;
      } else {
        y = Math.min(0, Math.max(viewH - contentH, y));
      }
    }

    function setScaleAround(nextScale, focalX, focalY) {
      nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
      var wasExpanded = isExpanded();

      // Leaving the resting frame: jump at least to fullscreen cover scale.
      // Zooming out below cover collapses back to the open-page frame (scale 1).
      if (Math.abs(nextScale - 1) > 0.001) {
        var cover = coverScaleForFullscreen();
        if (!wasExpanded) {
          nextScale = Math.max(nextScale, cover);
        } else if (nextScale < cover - 0.001) {
          nextScale = 1;
        }
      }

      if (nextScale === scale) {
        clampPan();
        applyTransform();
        return;
      }

      // Focal point is in current viewport coords; if we are about to expand /
      // collapse, remap into the post-layout viewport before clamping.
      var contentX = (focalX - x) / scale;
      var contentY = (focalY - y) / scale;
      scale = nextScale;

      var willExpand = Math.abs(scale - 1) > 0.001;
      if (wasExpanded !== willExpand) {
        syncChrome();
        // After layout flip, keep the same content point under the focal pixel
        // when possible; otherwise use the new viewport centre.
        focalX = willExpand ? (viewport.clientWidth / 2) : focalX;
        focalY = willExpand ? (viewport.clientHeight / 2) : focalY;
      }

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

    function normalizeWheelDeltaY(event) {
      var dy = event.deltaY;
      if (event.deltaMode === 1) {
        dy *= 16; // lines → px-ish
      } else if (event.deltaMode === 2) {
        dy *= viewport.clientHeight || 800; // pages
      }
      return dy;
    }

    function onWheel(event) {
      var dy = normalizeWheelDeltaY(event);
      if (!dy) {
        return;
      }

      var wantZoomIn = dy < 0;
      // Resting frame: only hijack wheel when zooming in (or trackpad pinch).
      // Zooming out at scale 1 lets the page scroll under the map.
      if (!isExpanded() && !wantZoomIn && !event.ctrlKey) {
        return;
      }

      event.preventDefault();

      var rect = viewport.getBoundingClientRect();
      var focalX = event.clientX - rect.left;
      var focalY = event.clientY - rect.top;
      var factor = Math.exp(-dy * WHEEL_ZOOM_SENSITIVITY);
      // Clamp per-event so a huge notch or trackpad fling doesn't jump too far.
      factor = Math.min(ZOOM_STEP, Math.max(1 / ZOOM_STEP, factor));
      setScaleAround(scale * factor, focalX, focalY);
    }

    function touchDistance(touches) {
      var a = touches[0];
      var b = touches[1];
      return Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY);
    }

    function touchMidpoint(touches) {
      var a = touches[0];
      var b = touches[1];
      var rect = viewport.getBoundingClientRect();
      return {
        x: (a.clientX + b.clientX) / 2 - rect.left,
        y: (a.clientY + b.clientY) / 2 - rect.top
      };
    }

    function onTouchStart(event) {
      if (event.touches.length !== 2) {
        return;
      }
      pinchStartDistance = Math.max(1, touchDistance(event.touches));
      pinchStartScale = scale;
      pinchWasExpanded = isExpanded();
      // Swallow the following click so pieces don't toggle after a pinch.
      didDrag = true;
      pointerActive = false;
      pointerId = null;
    }

    function onTouchMove(event) {
      if (event.touches.length !== 2 || !pinchStartDistance) {
        return;
      }
      event.preventDefault();

      var distance = Math.max(1, touchDistance(event.touches));
      var nextScale = pinchStartScale * (distance / pinchStartDistance);

      // Resting frame: only pinch-out (zoom in) starts cover mode.
      if (!isExpanded() && nextScale <= pinchStartScale) {
        return;
      }

      var mid = touchMidpoint(event.touches);
      setScaleAround(nextScale, mid.x, mid.y);

      // After expand/collapse the viewport layout jumps — re-base the gesture.
      if (pinchWasExpanded !== isExpanded()) {
        pinchStartDistance = distance;
        pinchStartScale = scale;
        pinchWasExpanded = isExpanded();
      }
    }

    function onTouchEnd(event) {
      if (event.touches.length < 2) {
        pinchStartDistance = 0;
      }
    }

    function onPointerDown(event) {
      if (event.button !== undefined && event.button !== 0) {
        return;
      }
      if (event.target.closest && event.target.closest('.zoom-controls')) {
        return;
      }
      // Two-finger pinch is owned by touch handlers.
      if (event.pointerType === 'touch' && pinchStartDistance) {
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
      if (!pointerActive || event.pointerId !== pointerId || pinchStartDistance) {
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
      var wasExpanded = isExpanded();
      measureBaseSize();
      scale = prevScale;
      if (wasExpanded) {
        var cover = coverScaleForFullscreen();
        if (scale < cover) {
          scale = cover;
        }
      }
      syncChrome();
      clampPan();
      applyTransform();
    }

    function init() {
      measureBaseSize();
      scale = 1;
      x = 0;
      y = 0;
      syncChrome();
      clampPan();
      applyTransform();

      viewport.addEventListener('pointerdown', onPointerDown);
      viewport.addEventListener('pointermove', onPointerMove);
      viewport.addEventListener('pointerup', onPointerUp);
      viewport.addEventListener('pointercancel', onPointerUp);
      viewport.addEventListener('touchstart', onTouchStart, { passive: true });
      viewport.addEventListener('touchmove', onTouchMove, { passive: false });
      viewport.addEventListener('touchend', onTouchEnd);
      viewport.addEventListener('touchcancel', onTouchEnd);
      // Capture on viewport so we see the click even if it targets a path.
      viewport.addEventListener('click', onClickCapture, true);
      // passive: false so preventDefault can stop page scroll while zooming.
      viewport.addEventListener('wheel', onWheel, { passive: false });
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
