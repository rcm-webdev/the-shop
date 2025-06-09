const express = require("express");
const router = express.Router();
const upload = require("../middleware/multer");
const postsController = require("../controllers/posts");
const { ensureAuth, ensureGuest } = require("../middleware/auth");

//Post Routes - simplified for now
router.get("/:id", ensureAuth, postsController.getPost);

router.post("/createPost", upload.fields([
  { name: 'frontImage', maxCount: 1 },
  { name: 'backImage', maxCount: 1 }
]), postsController.createPost);

// Handle both POST and PUT for updatePost
router.post("/updatePost/:id", ensureAuth, postsController.updatePost);
router.put("/updatePost/:id", ensureAuth, postsController.updatePost);

router.delete("/deletePost/:id", ensureAuth, postsController.deletePost);

// Google Sheets import routes
router.get("/import-sheet", ensureAuth, postsController.getImportStatus);
router.post("/import-sheet", ensureAuth, postsController.importFromGoogleSheet);

module.exports = router;
