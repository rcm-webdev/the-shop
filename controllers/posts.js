const cloudinary = require("../middleware/cloudinary");
const Post = require("../models/Post");

module.exports = {
  getProfile: async (req, res) => {
    try {
      const posts = await Post.find({ user: req.user.id });
      res.render("profile.ejs", { posts: posts, user: req.user });
    } catch (err) {
      console.log(err);
    }
  },
  getFeed: async (req, res) => {
    try {
      const query = req.query.tag ? { tags: req.query.tag } : {};
      const posts = await Post.find(query).sort({ createdAt: "desc" }).lean();
      res.render("feed.ejs", { posts: posts, selectedTag: req.query.tag });
    } catch (err) {
      console.log(err);
    }
  },
  getPost: async (req, res) => {
    try {
      const post = await Post.findById(req.params.id);
      res.render("post.ejs", { post: post, user: req.user });
    } catch (err) {
      console.log(err);
    }
  },
  createPost: async (req, res) => {
    try {
      // Validate request
      if (!req.files || !req.files.frontImage || !req.files.backImage) {
        console.log("Missing required images");
        return res.redirect("/profile");
      }

      if (!req.body.title || !req.body.caption) {
        console.log("Missing required fields");
        return res.redirect("/profile");
      }

      // Upload front image to cloudinary
      const frontResult = await cloudinary.uploader.upload(req.files.frontImage[0].path);
      console.log("Front image uploaded:", frontResult);

      // Upload back image to cloudinary
      const backResult = await cloudinary.uploader.upload(req.files.backImage[0].path);
      console.log("Back image uploaded:", backResult);

      // Create the post
      const post = await Post.create({
        title: req.body.title,
        frontImage: frontResult.secure_url,
        frontImageCloudinaryId: frontResult.public_id,
        backImage: backResult.secure_url,
        backImageCloudinaryId: backResult.public_id,
        caption: req.body.caption,
        likes: 0,
        tags: req.body.tags ? req.body.tags.split(',').map(tag => tag.trim()) : [],
        user: req.user.id,
      });

      console.log("Post has been added successfully:", post);
      res.redirect("/profile");
    } catch (err) {
      console.log(`Error creating post: ${err}`);
      return res.redirect("/profile");
    }
  },
  likePost: async (req, res) => {
    try {
      await Post.findOneAndUpdate(
        { _id: req.params.id },
        {
          $inc: { likes: 1 },
        }
      );
      console.log("Likes +1");
      res.redirect(`/post/${req.params.id}`);
    } catch (err) {
      console.log(err);
    }
  },
  deletePost: async (req, res) => {
    try {
      console.log(`Finding post with id: ${req.params.id}`);
      let post = await Post.findById({ _id: req.params.id });
      if (!post) {
        console.log(`Post not found with id: ${req.params.id}`);
        return res.redirect("/profile");
      }
      console.log(`Post found: ${post}`);

      // Delete both images from cloudinary
      await cloudinary.uploader.destroy(post.frontImageCloudinaryId);
      await cloudinary.uploader.destroy(post.backImageCloudinaryId);

      // Delete post from db
      console.log(`Deleting post with id: ${req.params.id}`);
      await Post.findOneAndDelete({ _id: req.params.id });
      console.log("Deleted Post");
      res.redirect("/profile");
    } catch (err) {
      console.log(`Error deleting post: ${err}`);
      res.redirect("/profile");
    }
  },
};
