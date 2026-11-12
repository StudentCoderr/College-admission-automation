/* Homepage swipe carousels + quick section navigator.
   Progressive enhancement: the tracks are still native horizontal scrollers
   without JavaScript, and every card remains reachable by touch or keyboard. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var reduceMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function scrollBehavior() {
      return reduceMotion ? "auto" : "smooth";
    }

    document.querySelectorAll("[data-carousel]").forEach(function (root) {
      var track = root.querySelector("[data-carousel-track]");
      if (!track) return;

      var prev = root.querySelector("[data-carousel-prev]");
      var next = root.querySelector("[data-carousel-next]");
      var progress = root.querySelector("[data-carousel-progress]");
      var items = Array.prototype.slice.call(track.children);
      if (!items.length) return;

      function trackPadding() {
        var style = window.getComputedStyle(track);
        return parseFloat(style.paddingLeft) || 0;
      }

      function maxScroll() {
        return Math.max(0, track.scrollWidth - track.clientWidth);
      }

      function itemLeft(item) {
        return (
          item.getBoundingClientRect().left -
          track.getBoundingClientRect().left +
          track.scrollLeft -
          trackPadding()
        );
      }

      function nearestIndex() {
        var best = 0;
        var distance = Infinity;
        items.forEach(function (item, index) {
          var delta = Math.abs(itemLeft(item) - track.scrollLeft);
          if (delta < distance) {
            distance = delta;
            best = index;
          }
        });
        return best;
      }

      function update() {
        var max = maxScroll();
        var scrollable = max > 4;
        root.classList.toggle("is-scrollable", scrollable);

        if (prev) prev.disabled = !scrollable || track.scrollLeft <= 2;
        if (next) next.disabled = !scrollable || track.scrollLeft >= max - 2;

        if (progress) {
          progress.style.width = max
            ? Math.min(100, Math.max(0, (track.scrollLeft / max) * 100)) + "%"
            : "0%";
        }
      }

      function scrollToItem(index) {
        var item = items[Math.max(0, Math.min(index, items.length - 1))];
        if (!item) return;
        var left = Math.max(0, itemLeft(item));
        if (typeof track.scrollTo === "function") {
          track.scrollTo({ left: left, behavior: scrollBehavior() });
        } else {
          track.scrollLeft = left;
        }
      }

      if (prev) {
        prev.addEventListener("click", function () {
          scrollToItem(nearestIndex() - 1);
        });
      }
      if (next) {
        next.addEventListener("click", function () {
          if (track.scrollLeft >= maxScroll() - 2) return;
          scrollToItem(nearestIndex() + 1);
        });
      }

      track.addEventListener(
        "scroll",
        function () {
          window.requestAnimationFrame(update);
        },
        { passive: true }
      );

      track.addEventListener("keydown", function (event) {
        if (event.key === "ArrowRight") {
          event.preventDefault();
          scrollToItem(nearestIndex() + 1);
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          scrollToItem(nearestIndex() - 1);
        }
      });

      window.addEventListener("resize", update);
      window.addEventListener("load", update);
      if (window.ResizeObserver) {
        new ResizeObserver(update).observe(track);
      }
      update();
    });

    // Highlight the matching quick-jump pill while the visitor scrolls.
    var jumpLinks = Array.prototype.slice.call(
      document.querySelectorAll('.home-jump a[href^="#"]')
    );
    if (jumpLinks.length && "IntersectionObserver" in window) {
      var linkById = {};
      jumpLinks.forEach(function (link) {
        linkById[link.getAttribute("href").slice(1)] = link;
      });

      var sections = Object.keys(linkById)
        .map(function (id) {
          return document.getElementById(id);
        })
        .filter(Boolean);

      function setActive(id) {
        jumpLinks.forEach(function (link) {
          link.classList.remove("is-active");
          link.removeAttribute("aria-current");
        });
        var active = linkById[id];
        if (active) {
          active.classList.add("is-active");
          active.setAttribute("aria-current", "location");
        }
      }

      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) setActive(entry.target.id);
          });
        },
        { rootMargin: "-28% 0px -58% 0px", threshold: 0 }
      );

      sections.forEach(function (section) {
        observer.observe(section);
      });
    }
  });
})();
