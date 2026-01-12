;;; org-gdocs-mode.el --- Sync org-mode documents with Google Docs -*- lexical-binding: t; -*-

;; Copyright (C) 2026

;; Author: org-gdocs-sync
;; Version: 0.1.0
;; Package-Requires: ((emacs "28.1") (org "9.0"))
;; Keywords: org, google-docs, sync
;; URL: https://github.com/your-repo/org-gdocs-sync

;;; Commentary:

;; A minor mode for org-mode buffers that enables synchronization with
;; Google Docs.  Provides push/pull commands, modeline status indicator,
;; and annotation navigation.
;;
;; The mode auto-enables on org files containing a #+GDOC_ID: header.
;;
;; Keybindings (C-c g prefix):
;;   C-c g g - DWIM (Do What I Mean)
;;   C-c g p - Push to Google Docs
;;   C-c g P - Pull comments/suggestions
;;   C-c g s - Refresh status
;;   C-c g o - Open in browser
;;   C-c g n - Next annotation
;;   C-c g N - Previous annotation
;;   C-c g r - Resolve comment at point
;;   C-c g i - Integrate suggestion at point

;;; Code:

(require 'org)

;;; Customization

(defgroup org-gdocs nil
  "Sync org-mode documents with Google Docs."
  :group 'org
  :prefix "org-gdocs-")

(defcustom org-gdocs-sync-command "uv run sync"
  "Command to run the sync CLI.
This should be the base command without subcommands or arguments."
  :type 'string
  :group 'org-gdocs)

(defcustom org-gdocs-auto-status t
  "If non-nil, fetch status when enabling the mode."
  :type 'boolean
  :group 'org-gdocs)

;;; Internal Variables

(defvar-local org-gdocs--status nil
  "Cached sync status plist for current buffer.
Contains keys like :pending-comments, :pending-suggestions, :last-sync.")

(defvar-local org-gdocs--syncing nil
  "Non-nil when a sync operation is in progress.")

(defvar-local org-gdocs--error nil
  "Non-nil if the last operation resulted in an error.")

(defvar-local org-gdocs--gdoc-id nil
  "Cached GDOC_ID for the current buffer.")

;;; Modeline

(defvar org-gdocs-mode-line-format
  '(:eval (org-gdocs--mode-line-string))
  "Mode line format for org-gdocs-mode.")

(put 'org-gdocs-mode-line-format 'risky-local-variable t)

(defun org-gdocs--mode-line-string ()
  "Generate modeline string based on current state."
  (when org-gdocs-mode
    (cond
     (org-gdocs--syncing
      (propertize "[GDocs:syncing...]" 'face 'org-gdocs-syncing-face))
     (org-gdocs--error
      (propertize "[GDocs:error]" 'face 'org-gdocs-error-face
                  'help-echo "Last sync operation failed. C-c g s to retry."))
     ((org-gdocs--buffer-modified-since-sync-p)
      (propertize "[GDocs:modified]" 'face 'org-gdocs-modified-face))
     (org-gdocs--status
      (let ((comments (or (plist-get org-gdocs--status :pending-comments) 0))
            (suggestions (or (plist-get org-gdocs--status :pending-suggestions) 0)))
        (propertize (format "[GDocs:synced %dc/%ds]" comments suggestions)
                    'face 'org-gdocs-synced-face
                    'help-echo (format "Last sync: %s\nComments: %d\nSuggestions: %d"
                                       (or (plist-get org-gdocs--status :last-sync) "unknown")
                                       comments suggestions))))
     (org-gdocs--gdoc-id
      (propertize "[GDocs:?]" 'face 'org-gdocs-unknown-face
                  'help-echo "Status unknown. C-c g s to refresh."))
     (t nil))))

;;; Faces

(defface org-gdocs-synced-face
  '((t :inherit success))
  "Face for synced status in modeline."
  :group 'org-gdocs)

(defface org-gdocs-modified-face
  '((t :inherit warning))
  "Face for modified status in modeline."
  :group 'org-gdocs)

(defface org-gdocs-syncing-face
  '((t :inherit font-lock-comment-face))
  "Face for syncing status in modeline."
  :group 'org-gdocs)

(defface org-gdocs-error-face
  '((t :inherit error))
  "Face for error status in modeline."
  :group 'org-gdocs)

(defface org-gdocs-unknown-face
  '((t :inherit shadow))
  "Face for unknown status in modeline."
  :group 'org-gdocs)

;;; Helper Functions

(defun org-gdocs--get-gdoc-id ()
  "Get GDOC_ID from buffer's org metadata."
  (save-excursion
    (save-restriction
      (widen)
      (goto-char (point-min))
      (when (re-search-forward "^#\\+GDOC_ID:\\s-*\\(.+\\)$" nil t)
        (string-trim (match-string-no-properties 1))))))

(defun org-gdocs--get-last-sync ()
  "Get LAST_SYNC timestamp from buffer's org metadata."
  (save-excursion
    (save-restriction
      (widen)
      (goto-char (point-min))
      (when (re-search-forward "^#\\+LAST_SYNC:\\s-*\\(.+\\)$" nil t)
        (string-trim (match-string-no-properties 1))))))

(defun org-gdocs--buffer-modified-since-sync-p ()
  "Return non-nil if buffer was modified since last sync."
  (and (buffer-modified-p)
       org-gdocs--gdoc-id))

(defun org-gdocs--get-document-url ()
  "Get the Google Docs URL for the current document."
  (when org-gdocs--gdoc-id
    (format "https://docs.google.com/document/d/%s/edit" org-gdocs--gdoc-id)))

;;; Async CLI Runner

(defcustom org-gdocs-debug nil
  "If non-nil, log debug messages to *org-gdocs-debug* buffer."
  :type 'boolean
  :group 'org-gdocs)

(defun org-gdocs--debug (format-string &rest args)
  "Log debug message if `org-gdocs-debug' is non-nil."
  (when org-gdocs-debug
    (with-current-buffer (get-buffer-create "*org-gdocs-debug*")
      (goto-char (point-max))
      (insert (format-time-string "[%H:%M:%S] "))
      (insert (apply #'format format-string args))
      (insert "\n"))))

(defun org-gdocs--run-async (subcommand &optional args callback)
  "Run sync SUBCOMMAND asynchronously with ARGS.
Call CALLBACK with parsed plist result when complete.
ARGS should be a list of additional arguments."
  (unless (buffer-file-name)
    (user-error "Buffer must be visiting a file"))
  (when org-gdocs--syncing
    (user-error "A sync operation is already in progress"))
  (let* ((file (buffer-file-name))
         (buf (current-buffer))
         (output-buffer (generate-new-buffer "*org-gdocs-output*"))
         (cmd-parts (split-string org-gdocs-sync-command))
         (full-cmd (append cmd-parts
                           (list subcommand)
                           args
                           (list file)))
         ;; Ensure common paths are in exec-path for GUI Emacs
         (exec-path (append exec-path '("/usr/local/bin" "/opt/homebrew/bin"
                                        "~/.local/bin" "~/.cargo/bin")))
         (process-environment (cons (format "PATH=%s" (string-join exec-path ":"))
                                    process-environment)))
    (org-gdocs--debug "Running command: %S" full-cmd)
    (org-gdocs--debug "exec-path: %S" exec-path)
    (setq org-gdocs--syncing t)
    (setq org-gdocs--error nil)
    (force-mode-line-update)
    (make-process
     :name "org-gdocs-sync"
     :buffer output-buffer
     :command full-cmd
     :stderr (get-buffer-create "*org-gdocs-stderr*")
     :sentinel
     (lambda (proc _event)
       (org-gdocs--debug "Process event: %s, status: %s" _event (process-status proc))
       (when (eq (process-status proc) 'exit)
         (let ((exit-code (process-exit-status proc))
               (raw-output "")
               result)
           (org-gdocs--debug "Exit code: %d" exit-code)
           (when (buffer-live-p output-buffer)
             (with-current-buffer output-buffer
               (setq raw-output (buffer-string))
               (org-gdocs--debug "Raw output (%d chars): %s"
                                 (length raw-output)
                                 (if (> (length raw-output) 500)
                                     (concat (substring raw-output 0 500) "...")
                                   raw-output))
               (goto-char (point-min))
               (condition-case err
                   (setq result (read (current-buffer)))
                 (error
                  (org-gdocs--debug "Parse error: %S" err)
                  (setq result `(:status "error"
                                 :message ,(format "Failed to parse output: %s\nRaw: %s"
                                                   (error-message-string err)
                                                   raw-output)))))))
           ;; Don't kill buffer on error for debugging
           (if (and (not org-gdocs-debug) (buffer-live-p output-buffer))
               (kill-buffer output-buffer))
           ;; Update state in the original buffer
           (when (buffer-live-p buf)
             (with-current-buffer buf
               (setq org-gdocs--syncing nil)
               (if (or (not (eq exit-code 0))
                       (equal (plist-get result :status) "error"))
                   (progn
                     (setq org-gdocs--error t)
                     (message "org-gdocs: %s"
                              (or (plist-get result :message) "Operation failed")))
                 (setq org-gdocs--error nil))
               (force-mode-line-update)
               (when callback
                 (funcall callback result))))))))))

;;; Commands

(defun org-gdocs-push ()
  "Push current buffer to Google Docs."
  (interactive)
  (save-buffer)
  (message "Pushing to Google Docs...")
  (org-gdocs--run-async
   "push" nil
   (lambda (result)
     (if (equal (plist-get result :status) "success")
         (progn
           (message "Pushed successfully. %d requests sent."
                    (or (plist-get result :requests-sent) 0))
           ;; Refresh status after push
           (org-gdocs-status))
       (message "Push failed: %s" (plist-get result :message))))))

(defun org-gdocs-pull ()
  "Pull comments and suggestions from Google Docs."
  (interactive)
  (when (buffer-modified-p)
    (if (yes-or-no-p "Buffer modified. Save before pulling? ")
        (save-buffer)
      (user-error "Pull aborted")))
  (message "Pulling from Google Docs...")
  (org-gdocs--run-async
   "pull" '("--backup")
   (lambda (result)
     (if (equal (plist-get result :status) "success")
         (progn
           (revert-buffer t t t)
           (message "Pulled %d comments, %d suggestions."
                    (or (plist-get result :comments-pulled) 0)
                    (or (plist-get result :suggestions-pulled) 0))
           ;; Refresh status after pull
           (org-gdocs-status))
       (message "Pull failed: %s" (plist-get result :message))))))

(defun org-gdocs-status ()
  "Refresh sync status for current buffer."
  (interactive)
  (org-gdocs--run-async
   "status" nil
   (lambda (result)
     (setq org-gdocs--status result)
     (force-mode-line-update)
     (when (called-interactively-p 'interactive)
       (message "Status: %dc/%ds pending"
                (or (plist-get result :pending-comments) 0)
                (or (plist-get result :pending-suggestions) 0))))))

(defun org-gdocs-open ()
  "Open the linked Google Doc in a browser."
  (interactive)
  (let ((url (org-gdocs--get-document-url)))
    (if url
        (browse-url url)
      (user-error "No GDOC_ID found in buffer"))))

;;; Annotation Navigation

(defun org-gdocs--in-annotations-section-p ()
  "Return non-nil if point is in GDOCS_ANNOTATIONS section."
  (save-excursion
    (when (org-before-first-heading-p)
      (cl-return-from org-gdocs--in-annotations-section-p nil))
    (org-back-to-heading t)
    (let ((heading (org-get-heading t t t t)))
      (or (string= heading "GDOCS_ANNOTATIONS")
          (save-excursion
            (and (org-up-heading-safe)
                 (string= (org-get-heading t t t t) "GDOCS_ANNOTATIONS")))))))

(defun org-gdocs--find-annotations-section ()
  "Find and return the position of GDOCS_ANNOTATIONS heading, or nil."
  (save-excursion
    (goto-char (point-min))
    (when (re-search-forward "^\\*+\\s-+GDOCS_ANNOTATIONS\\s-*$" nil t)
      (line-beginning-position))))

(defun org-gdocs--annotation-at-point-p ()
  "Return non-nil if point is at an annotation heading."
  (and (org-at-heading-p)
       (org-entry-get nil "COMMENT_ID")))

(defun org-gdocs--collect-annotations ()
  "Return list of annotation positions with their properties.
Each element is (POS COMMENT-ID ANCHOR RESOLVED)."
  (let ((annotations-pos (org-gdocs--find-annotations-section))
        results)
    (when annotations-pos
      (save-excursion
        (goto-char annotations-pos)
        (let ((section-end (save-excursion
                             (org-end-of-subtree t t)
                             (point))))
          (while (re-search-forward "^\\*\\*\\*\\s-+" section-end t)
            (let ((pos (line-beginning-position))
                  (comment-id (org-entry-get nil "COMMENT_ID"))
                  (sugg-id (org-entry-get nil "SUGG_ID"))
                  (anchor (org-entry-get nil "ANCHOR"))
                  (resolved (org-entry-get nil "RESOLVED")))
              (when (or comment-id sugg-id)
                (push (list pos (or comment-id sugg-id) anchor resolved) results)))))))
    (nreverse results)))

(defun org-gdocs--preview-annotation ()
  "Show annotation preview in echo area."
  (let ((heading (org-get-heading t t t t))
        (anchor (org-entry-get nil "ANCHOR"))
        (resolved (org-entry-get nil "RESOLVED")))
    (message "%s%s\n   Re: \"%s\""
             (if (equal resolved "t") "[RESOLVED] " "")
             heading
             (if (and anchor (not (string-empty-p anchor)))
                 (truncate-string-to-width anchor 60 nil nil "...")
               "[unanchored comment]"))))

(defun org-gdocs-next-annotation ()
  "Jump to next annotation and show preview."
  (interactive)
  (let ((annotations (org-gdocs--collect-annotations))
        (pos (point))
        target)
    (unless annotations
      (user-error "No annotations found"))
    (setq target (cl-find-if (lambda (a) (> (car a) pos)) annotations))
    (unless target
      (setq target (car annotations))
      (message "Wrapped to first annotation"))
    (goto-char (car target))
    (org-show-entry)
    (org-show-children)
    (recenter)
    (org-gdocs--preview-annotation)))

(defun org-gdocs-prev-annotation ()
  "Jump to previous annotation and show preview."
  (interactive)
  (let ((annotations (org-gdocs--collect-annotations))
        (pos (point))
        target)
    (unless annotations
      (user-error "No annotations found"))
    (setq target (cl-find-if (lambda (a) (< (car a) pos)) (reverse annotations)))
    (unless target
      (setq target (car (last annotations)))
      (message "Wrapped to last annotation"))
    (goto-char (car target))
    (org-show-entry)
    (org-show-children)
    (recenter)
    (org-gdocs--preview-annotation)))

;;; Resolve/Integrate Commands

(defun org-gdocs--get-annotation-id-at-point ()
  "Get the comment or suggestion ID at point."
  (or (org-entry-get nil "COMMENT_ID")
      (org-entry-get nil "SUGG_ID")))

(defun org-gdocs-resolve ()
  "Resolve the comment at point."
  (interactive)
  (let ((comment-id (org-entry-get nil "COMMENT_ID")))
    (unless comment-id
      (user-error "No comment at point"))
    (when (equal (org-entry-get nil "RESOLVED") "t")
      (user-error "Comment is already resolved"))
    (message "Resolving comment...")
    (org-gdocs--run-async
     "resolve" (list comment-id)
     (lambda (result)
       (if (equal (plist-get result :status) "success")
           (progn
             (revert-buffer t t t)
             (message "Comment resolved."))
         (message "Resolve failed: %s" (plist-get result :message)))))))

(defun org-gdocs-integrate ()
  "Integrate the suggestion at point."
  (interactive)
  (let ((sugg-id (org-entry-get nil "SUGG_ID")))
    (unless sugg-id
      (user-error "No suggestion at point"))
    (when (equal (org-entry-get nil "STATUS") "integrated")
      (user-error "Suggestion is already integrated"))
    (message "Marking suggestion as integrated...")
    (org-gdocs--run-async
     "integrate" (list sugg-id)
     (lambda (result)
       (if (equal (plist-get result :status) "success")
           (progn
             (revert-buffer t t t)
             (message "Suggestion marked as integrated."))
         (message "Integrate failed: %s" (plist-get result :message)))))))

;;; DWIM Command

(defun org-gdocs-dwim ()
  "Do What I Mean: context-aware sync action.

- If at an annotation, prompt to resolve/integrate
- If buffer is modified, push
- Otherwise, pull to check for new feedback"
  (interactive)
  (cond
   ;; At an annotation - offer to resolve or integrate
   ((and (org-gdocs--in-annotations-section-p)
         (org-gdocs--annotation-at-point-p))
    (let ((comment-id (org-entry-get nil "COMMENT_ID"))
          (sugg-id (org-entry-get nil "SUGG_ID")))
      (cond
       (comment-id
        (if (equal (org-entry-get nil "RESOLVED") "t")
            (message "Comment already resolved.")
          (when (yes-or-no-p "Resolve this comment? ")
            (org-gdocs-resolve))))
       (sugg-id
        (if (equal (org-entry-get nil "STATUS") "integrated")
            (message "Suggestion already integrated.")
          (when (yes-or-no-p "Mark suggestion as integrated? ")
            (org-gdocs-integrate)))))))
   ;; Buffer modified - push
   ((buffer-modified-p)
    (when (yes-or-no-p "Buffer modified. Push to Google Docs? ")
      (org-gdocs-push)))
   ;; Default - pull
   (t
    (when (yes-or-no-p "Pull latest from Google Docs? ")
      (org-gdocs-pull)))))

;;; Keymap

(defvar org-gdocs-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c g g") #'org-gdocs-dwim)
    (define-key map (kbd "C-c g p") #'org-gdocs-push)
    (define-key map (kbd "C-c g P") #'org-gdocs-pull)
    (define-key map (kbd "C-c g s") #'org-gdocs-status)
    (define-key map (kbd "C-c g o") #'org-gdocs-open)
    (define-key map (kbd "C-c g n") #'org-gdocs-next-annotation)
    (define-key map (kbd "C-c g N") #'org-gdocs-prev-annotation)
    (define-key map (kbd "C-c g r") #'org-gdocs-resolve)
    (define-key map (kbd "C-c g i") #'org-gdocs-integrate)
    map)
  "Keymap for `org-gdocs-mode'.")

;;; Minor Mode Definition

;;;###autoload
(define-minor-mode org-gdocs-mode
  "Minor mode for syncing org-mode documents with Google Docs.

\\{org-gdocs-mode-map}"
  :lighter nil  ; We use custom modeline format
  :keymap org-gdocs-mode-map
  :group 'org-gdocs
  (if org-gdocs-mode
      (progn
        ;; Enable
        (setq org-gdocs--gdoc-id (org-gdocs--get-gdoc-id))
        (unless org-gdocs--gdoc-id
          (setq org-gdocs-mode nil)
          (user-error "No #+GDOC_ID: found in buffer"))
        ;; Add modeline indicator
        (add-to-list 'mode-line-misc-info '("" org-gdocs-mode-line-format) t)
        ;; Fetch initial status
        (when org-gdocs-auto-status
          (org-gdocs-status)))
    ;; Disable
    (setq org-gdocs--gdoc-id nil)
    (setq org-gdocs--status nil)
    (setq org-gdocs--syncing nil)
    (setq org-gdocs--error nil)
    (setq mode-line-misc-info
          (delete '("" org-gdocs-mode-line-format) mode-line-misc-info))))

;;; Auto-enable

;;;###autoload
(defun org-gdocs--maybe-enable ()
  "Enable `org-gdocs-mode' if buffer has GDOC_ID."
  (when (and (derived-mode-p 'org-mode)
             (buffer-file-name)
             (org-gdocs--get-gdoc-id))
    (org-gdocs-mode 1)))

;;;###autoload
(add-hook 'org-mode-hook #'org-gdocs--maybe-enable)

(provide 'org-gdocs-mode)
;;; org-gdocs-mode.el ends here
