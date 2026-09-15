// Confirm before deleting a student. The server re-checks everything
// regardless — this is just to stop accidental clicks.
document.querySelectorAll(".js-confirm-delete").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    var name = form.getAttribute("data-student-name") || "this student";
    var confirmed = window.confirm("Are you sure you want to delete " + name + "?");
    if (!confirmed) {
      event.preventDefault();
    }
  });
});

// Basic client-side validation for the add/edit student form.
var studentForm = document.getElementById("student-form");
if (studentForm) {
  studentForm.addEventListener("submit", function (event) {
    var errors = [];

    var requiredFields = [
      ["student_id", "Student ID"],
      ["student_name", "Student name"],
      ["email", "Email"],
      ["course", "Course"],
      ["semester", "Semester"]
    ];

    requiredFields.forEach(function (pair) {
      var field = studentForm.querySelector('[name="' + pair[0] + '"]');
      if (field && !field.value.trim()) {
        errors.push(pair[1] + " is required.");
      }
    });

    var email = studentForm.querySelector('[name="email"]');
    if (email && email.value.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) {
      errors.push("Please enter a valid email address.");
    }

    var semester = studentForm.querySelector('[name="semester"]');
    if (semester && semester.value) {
      var semNum = parseInt(semester.value, 10);
      if (isNaN(semNum) || semNum < 1 || semNum > 6) {
        errors.push("Semester must be a number between 1 and 6.");
      }
    }

    var errorBox = document.getElementById("client-errors");
    if (errors.length > 0) {
      event.preventDefault();
      if (errorBox) {
        errorBox.innerHTML = "";
        errors.forEach(function (message) {
          var li = document.createElement("li");
          li.className = "flash flash-error";
          li.textContent = message;
          errorBox.appendChild(li);
        });
      }
    }
  });
}

// Auto-dismiss success flash messages after a few seconds.
document.querySelectorAll(".flash-success").forEach(function (el) {
  setTimeout(function () {
    el.style.transition = "opacity 0.4s ease";
    el.style.opacity = "0";
    setTimeout(function () {
      el.remove();
    }, 400);
  }, 4000);
});

// Mobile Sidebar Drawer Controller
document.addEventListener("DOMContentLoaded", function () {
  var mobileMenuBtn = document.getElementById("mobileMenuBtn");
  var drawerCloseBtn = document.getElementById("drawerCloseBtn");
  var mobileDrawer = document.getElementById("mobileDrawer");
  var mobileOverlay = document.getElementById("mobileOverlay");

  function openDrawer() {
    if (mobileDrawer) mobileDrawer.classList.add("is-active");
    if (mobileOverlay) mobileOverlay.classList.add("is-active");
    document.body.classList.add("drawer-open");
  }

  function closeDrawer() {
    if (mobileDrawer) mobileDrawer.classList.remove("is-active");
    if (mobileOverlay) mobileOverlay.classList.remove("is-active");
    document.body.classList.remove("drawer-open");
  }

  if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener("click", openDrawer);
  }

  if (drawerCloseBtn) {
    drawerCloseBtn.addEventListener("click", closeDrawer);
  }

  if (mobileOverlay) {
    mobileOverlay.addEventListener("click", closeDrawer);
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeDrawer();
    }
  });

  if (mobileDrawer) {
    mobileDrawer.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeDrawer);
    });
  }
});

// ---------------------------------------------------------------------------
// Global Search Live Controller
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
  var searchInput = document.getElementById("globalSearchInput");
  var searchDropdown = document.getElementById("globalSearchResults");
  var searchClear = document.getElementById("globalSearchClear");

  if (!searchInput || !searchDropdown) return;

  var debounceTimer = null;
  var currentQuery = "";
  var selectedIndex = -1;

  function clearSearch() {
    searchInput.value = "";
    currentQuery = "";
    searchDropdown.innerHTML = "";
    searchDropdown.style.display = "none";
    if (searchClear) searchClear.style.display = "none";
    selectedIndex = -1;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderCategoryGroup(categoryTitle, items) {
    if (!items || items.length === 0) return "";
    var html = '<div class="search-group">';
    html += '<div class="search-group-header">' + categoryTitle + '</div>';
    items.forEach(function (item) {
      html += '<a href="' + item.url + '" class="search-item-row">';
      html += '<div class="search-item-content">';
      html += '<div class="search-item-title">' + escapeHtml(item.title) + '</div>';
      if (item.subtitle) {
        html += '<div class="search-item-subtitle">' + escapeHtml(item.subtitle) + '</div>';
      }
      if (item.detail) {
        html += '<div class="search-item-detail">' + escapeHtml(item.detail) + '</div>';
      }
      html += '</div>';
      if (item.action_text) {
        html += '<div class="search-item-action">' + escapeHtml(item.action_text) + ' &rarr;</div>';
      }
      html += '</a>';
    });
    html += '</div>';
    return html;
  }

  function performSearch(query) {
    if (query === currentQuery && searchDropdown.style.display === "block") return;
    currentQuery = query;

    searchDropdown.innerHTML = '<div class="search-loading-state">Searching...</div>';
    searchDropdown.style.display = "block";

    fetch("/api/global-search?q=" + encodeURIComponent(query))
      .then(function (res) {
        if (!res.ok) throw new Error("Search request failed");
        return res.json();
      })
      .then(function (data) {
        var results = data.results || {};
        var html = "";

        html += renderCategoryGroup("STUDENTS", results.students);
        html += renderCategoryGroup("EXAMS", results.exams);
        html += renderCategoryGroup("RESULTS", results.results);
        html += renderCategoryGroup("FEES", results.fees);
        html += renderCategoryGroup("NOTICES", results.notices);
        html += renderCategoryGroup("CERTIFICATES", results.certificates);
        html += renderCategoryGroup("AUDIT LOGS", results.audit_logs);

        if (!html) {
          html = '<div class="search-no-results">No results found for "' + escapeHtml(query) + '"</div>';
        }

        searchDropdown.innerHTML = html;
        searchDropdown.style.display = "block";
        selectedIndex = -1;
      })
      .catch(function (err) {
        searchDropdown.innerHTML = '<div class="search-no-results">Search failed. Please try again.</div>';
      });
  }

  searchInput.addEventListener("input", function () {
    var val = searchInput.value.trim();

    if (searchClear) {
      searchClear.style.display = val.length > 0 ? "block" : "none";
    }

    if (val.length < 2) {
      currentQuery = "";
      searchDropdown.innerHTML = "";
      searchDropdown.style.display = "none";
      clearTimeout(debounceTimer);
      return;
    }

    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      performSearch(val);
    }, 250);
  });

  if (searchClear) {
    searchClear.addEventListener("click", clearSearch);
  }

  searchInput.addEventListener("keydown", function (e) {
    var items = searchDropdown.querySelectorAll(".search-item-row");
    if (items.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = (selectedIndex + 1) % items.length;
      updateFocusedItem(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = (selectedIndex - 1 + items.length) % items.length;
      updateFocusedItem(items);
    } else if (e.key === "Enter") {
      if (selectedIndex >= 0 && selectedIndex < items.length) {
        e.preventDefault();
        items[selectedIndex].click();
      }
    } else if (e.key === "Escape") {
      clearSearch();
    }
  });

  function updateFocusedItem(items) {
    items.forEach(function (el, idx) {
      if (idx === selectedIndex) {
        el.classList.add("active-focused");
        el.scrollIntoView({ block: "nearest" });
      } else {
        el.classList.remove("active-focused");
      }
    });
  }

  document.addEventListener("click", function (e) {
    var wrap = document.querySelector(".global-search-bar-wrap");
    if (wrap && !wrap.contains(e.target)) {
      searchDropdown.style.display = "none";
    }
  });

  // Top Performers Widget Semester Switcher
  var semSelect = document.getElementById("topPerformersSemSelect");
  if (semSelect) {
    semSelect.addEventListener("change", function () {
      var sem = this.value;
      var viewLink = document.getElementById("viewFullRankingLink");
      if (viewLink) {
        viewLink.href = "/rankings?semester=" + sem;
      }
      fetch("/api/student-rankings?semester=" + sem)
        .then(function (res) { return res.json(); })
        .then(function (data) {
          var container = document.getElementById("topPerformersList");
          if (!container) return;
          if (data.success && data.rankings && data.rankings.length > 0) {
            var top3 = data.rankings.slice(0, 3);
            var html = '<div class="top-performers-list" style="display: flex; flex-direction: column; gap: 8px; margin-top: 8px;">';
            top3.forEach(function (p) {
              var badge = p.rank === 1 ? '🥇' : (p.rank === 2 ? '🥈' : (p.rank === 3 ? '🥉' : '#' + p.rank));
              html += '<div class="performer-row" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; background: var(--bg-page); border: 1px solid var(--border); box-sizing: border-box;">';
              html += '  <div style="display: flex; align-items: center; gap: 8px;">';
              html += '    <span class="performer-badge" style="font-size: 16px; font-weight: 700; min-width: 24px;">' + badge + '</span>';
              html += '    <div>';
              html += '      <a href="/students/' + p.record_id + '" style="font-weight: 600; color: var(--text-primary); text-decoration: none; font-size: 13px;">' + escapeHtml(p.student_name) + '</a>';
              html += '      <div style="font-size: 11px; color: var(--text-secondary);">' + escapeHtml(p.student_id) + ' &bull; ' + escapeHtml(p.course) + '</div>';
              html += '    </div>';
              html += '  </div>';
              html += '  <div style="text-align: right;">';
              html += '    <div style="font-weight: 700; color: var(--accent); font-size: 13px;">' + escapeHtml(p.formatted_marks) + '</div>';
              html += '    <div style="font-size: 11px; font-weight: 600; color: var(--text-primary);">' + escapeHtml(p.formatted_percentage) + '</div>';
              html += '  </div>';
              html += '</div>';
            });
            html += '</div>';
            container.innerHTML = html;
          } else {
            container.innerHTML = '<div class="empty-state" style="padding: 20px 12px; font-size: 13px;">No ranking available for this semester yet.</div>';
          }
        })
        .catch(function (err) {
          console.error("Error updating top performers widget:", err);
        });
    });
  }
});

