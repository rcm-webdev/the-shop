const cloudinary = require("../middleware/cloudinary");
const Post = require("../models/Post");
const googleService = require("../services/googleService");

module.exports = {
  getProfile: async (req, res) => {
    try {
      const posts = await Post.find({ user: req.user.id });
      
      res.render("profile.ejs", { 
        posts: posts, 
        user: req.user
      });
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

      // Upload front image to cloudinary
      const frontResult = await cloudinary.uploader.upload(
        `data:${req.files.frontImage[0].mimetype};base64,${req.files.frontImage[0].buffer.toString('base64')}`,
        { resource_type: "image" }
      );

      // Upload back image to cloudinary
      const backResult = await cloudinary.uploader.upload(
        `data:${req.files.backImage[0].mimetype};base64,${req.files.backImage[0].buffer.toString('base64')}`,
        { resource_type: "image" }
      );

      // Process tags if provided
      let tags = req.body.tags ? req.body.tags.split(',').map(tag => tag.trim()) : [];
      let wheelVariations = req.body.wheelVariations ? req.body.wheelVariations.split(',').map(v => v.trim()) : [];

      // Create the post
      const post = await Post.create({
        title: req.body.title || "Untitled",
        frontImage: frontResult.secure_url,
        frontImageCloudinaryId: frontResult.public_id,
        backImage: backResult.secure_url,
        backImageCloudinaryId: backResult.public_id,
        caption: req.body.caption || '',
        tags: tags,
        wheelVariations: wheelVariations,
        toyNumber: req.body.toyNumber || '',
        year: req.body.year || null,
        series: req.body.series || '',
        condition: req.body.condition || '',
        isSold: req.body.isSold === 'on',
        boxNumber: req.body.boxNumber || '',
        user: req.user.id,
      });

      console.log("Post has been added successfully");
      res.redirect("/profile");
    } catch (err) {
      console.log("Error creating post:", err);
      return res.redirect("/profile");
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
  updatePost: async (req, res) => {
    try {
      // Validate request
      if (!req.body.title || !req.body.caption) {
        console.log("Missing required fields");
        return res.redirect(`/post/${req.params.id}`);
      }

      // Process tags and wheel variations if provided
      let tags = req.body.tags ? req.body.tags.split(',').map(tag => tag.trim()) : [];
      let wheelVariations = req.body.wheelVariations ? req.body.wheelVariations.split(',').map(v => v.trim()) : [];

      // Update the post
      await Post.findOneAndUpdate(
        { _id: req.params.id },
        {
          title: req.body.title,
          caption: req.body.caption,
          tags: tags,
          wheelVariations: wheelVariations,
          toyNumber: req.body.toyNumber || '',
          year: req.body.year || null,
          series: req.body.series || '',
          condition: req.body.condition || '',
          isSold: req.body.isSold === 'on',
          boxNumber: req.body.boxNumber || '',
        }
      );

      console.log("Post has been updated");
      res.redirect(`/post/${req.params.id}`);
    } catch (err) {
      console.log(err);
      res.redirect(`/post/${req.params.id}`);
    }
  },
  getImportStatus: async (req, res) => {
    try {
      // Return information about available sheets and import requirements
      return res.json({
        success: true,
        availableSheets: {
          "App-Test-4": 4
        },
        requiredColumns: [
          "Box #",
          "Toy #",
          "Model Name",
          "Origin",
          "Series",
          "Wheel Variations",
          "Front Image",
          "Back Image"
        ],
        defaultSheetIndex: 4
      });
    } catch (error) {
      console.error("Error getting import status:", error);
      return res.status(500).json({
        success: false,
        error: "Failed to get import status",
        details: error.message
      });
    }
  },
  importFromGoogleSheet: async (req, res) => {
    try {
      let posts = [];
      const sheetIndex = req.body.sheetIndex || 4; // Default to App-Test-4 sheet
      
      console.log(`Starting import from sheet index: ${sheetIndex}`);
      
      // Import from sheet
      try {
        posts = await googleService.importSheet(sheetIndex);
        console.log(`Successfully fetched ${posts.length} posts from sheet`);
        console.log('First post data:', JSON.stringify(posts[0], null, 2));
      } catch (error) {
        console.error('Error fetching from sheet:', error);
        return res.status(500).json({
          success: false,
          error: "Failed to import from sheet",
          details: error.message
        });
      }
      
      // Create posts in the database
      const createdPosts = [];
      const errors = [];

      console.log(`Attempting to create ${posts.length} posts in database`);

      for (const postData of posts) {
        try {
          // Add the user ID to each post
          postData.user = req.user.id;

          // Extract Cloudinary IDs from URLs
          if (postData.frontImage && postData.frontImage.includes('cloudinary.com')) {
            const urlParts = postData.frontImage.split('/');
            const publicIdWithExt = urlParts[urlParts.length - 1];
            postData.frontImageCloudinaryId = publicIdWithExt.split('.')[0];
          } else {
            throw new Error('Front image must be a Cloudinary URL');
          }

          if (postData.backImage && postData.backImage.includes('cloudinary.com')) {
            const urlParts = postData.backImage.split('/');
            const publicIdWithExt = urlParts[urlParts.length - 1];
            postData.backImageCloudinaryId = publicIdWithExt.split('.')[0];
          } else {
            throw new Error('Back image must be a Cloudinary URL');
          }
          
          console.log('Creating post with data:', JSON.stringify(postData, null, 2));
          
          // Create the post
          const post = await Post.create(postData);
          console.log('Successfully created post:', post._id);
          createdPosts.push(post);
        } catch (error) {
          console.error('Error creating post:', error);
          errors.push({
            data: postData,
            error: error.message
          });
        }
      }

      console.log(`Import complete. Created: ${createdPosts.length}, Failed: ${errors.length}`);

      return res.json({
        success: true,
        importedCount: createdPosts.length,
        created: createdPosts,
        failed: errors.length,
        errors: errors
      });

    } catch (error) {
      console.error("Error importing from Google Sheet:", error);
      return res.status(500).json({ 
        success: false,
        error: "Failed to import from Google Sheet",
        details: error.message 
      });
    }
  },
};
