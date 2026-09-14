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
