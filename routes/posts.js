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

router.put("/likePost/:id", ensureAuth, postsController.likePost);

router.delete("/deletePost/:id", ensureAuth, postsController.deletePost);

module.exports = router;
