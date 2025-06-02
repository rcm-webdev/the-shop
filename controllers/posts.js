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

      console.log("Uploading front image...");
      // Upload front image to cloudinary with Advanced OCR
      const frontResult = await cloudinary.uploader.upload(
        `data:${req.files.frontImage[0].mimetype};base64,${req.files.frontImage[0].buffer.toString('base64')}`,
        {
          resource_type: "image",
          ocr: "adv_ocr"
        }
      );
      console.log("Front image uploaded with text detection:", frontResult);

      console.log("Uploading back image...");
      // Upload back image to cloudinary with Advanced OCR
      const backResult = await cloudinary.uploader.upload(
        `data:${req.files.backImage[0].mimetype};base64,${req.files.backImage[0].buffer.toString('base64')}`,
        {
          resource_type: "image",
          ocr: "adv_ocr"
        }
      );
      console.log("Back image uploaded with text detection:", backResult);

      // Extract text from the OCR results with position information
      const frontTextInfo = extractTextFromOCR(frontResult, true);
      const backTextInfo = extractTextFromOCR(backResult, true);
      
      console.log("Extracted text from front image:", frontTextInfo);
      console.log("Extracted text from back image:", backTextInfo);

      // Process text to extract relevant information
      const extractedInfo = processExtractedText(frontTextInfo, backTextInfo);
      console.log("Processed extracted info:", extractedInfo);

      if (!extractedInfo.carModel) {
        console.log("No car model could be detected from the images");
        req.flash("errors", { msg: "Could not detect car model from images. Please provide a title manually." });
        return res.redirect("/profile");
      }

      // Use provided title or generated title
      const title = req.body.title || extractedInfo.title || extractedInfo.carModel;

      // Combine user-provided tags with extracted tags
      let userTags = req.body.tags ? req.body.tags.split(',').map(tag => tag.trim()) : [];
      let extractedTags = [
        extractedInfo.carModel,
        extractedInfo.series,
        extractedInfo.toyNumber,
        extractedInfo.collection,
        extractedInfo.year
      ].filter(tag => tag); // Remove empty values

      let tags = [...new Set([...userTags, ...extractedTags])]; // Combine and remove duplicates

      console.log("Creating post with data:", {
        title,
        tags,
        caption: req.body.caption || extractedInfo.description || ''
      });

      // Create the post
      const post = await Post.create({
        title: title,
        frontImage: frontResult.secure_url,
        frontImageCloudinaryId: frontResult.public_id,
        backImage: backResult.secure_url,
        backImageCloudinaryId: backResult.public_id,
        caption: req.body.caption || extractedInfo.description || '',
        tags: tags,
        user: req.user.id,
      });

      console.log("Post has been added successfully:", post);
      res.redirect("/profile");
    } catch (err) {
      console.log("Detailed error:", {
        message: err.message,
        stack: err.stack,
        details: err
      });
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

      // Process tags if provided
      let tags = req.body.tags ? req.body.tags.split(',').map(tag => tag.trim()) : [];

      // Update the post
      await Post.findOneAndUpdate(
        { _id: req.params.id },
        {
          title: req.body.title,
          caption: req.body.caption,
          tags: tags,
        }
      );

      console.log("Post has been updated");
      res.redirect(`/post/${req.params.id}`);
    } catch (err) {
      console.log(err);
      res.redirect(`/post/${req.params.id}`);
    }
  }
};

// Helper function to extract text from OCR results with position information
function extractTextFromOCR(result, includePosition = false) {
  try {
    if (result?.info?.ocr?.adv_ocr?.status === 'complete') {
      const data = result.info.ocr.adv_ocr.data || [];
      return data.map(block => {
        const annotations = block.textAnnotations || [];
        return annotations.map(annotation => ({
          text: annotation.description.trim(),
          boundingBox: includePosition ? annotation.boundingBox : null,
          confidence: annotation.confidence
        })).filter(item => item.text);
      }).flat();
    }
    return [];
  } catch (error) {
    console.log("Error extracting OCR text:", error);
    return [];
  }
}

// Helper function to process extracted text
function processExtractedText(frontText, backText) {
  const result = {
    carModel: '',
    series: '',
    toyNumber: '',
    collection: '',
    year: '',
    title: '',
    description: ''
  };

  // Common patterns in Hot Wheels cards
  const patterns = {
    toyNumber: /[A-Z0-9]{3,}/,
    series: /(20\d{2}|[A-Z\s]+\s*Series)/i,
    year: /20\d{2}/,
    collection: /(Treasure Hunt|Super Treasure Hunt|Mainline|Premium)/i
  };

  // Process front text (usually contains car model and series)
  const frontTextItems = frontText.sort((a, b) => {
    // Sort by vertical position (y-coordinate) and confidence
    const aY = a.boundingBox ? a.boundingBox.y : 0;
    const bY = b.boundingBox ? b.boundingBox.y : 0;
    if (Math.abs(aY - bY) < 10) { // If items are roughly on the same line
      return b.confidence - a.confidence; // Sort by confidence
    }
    return aY - bY; // Sort by vertical position
  });

  // First line of text is often the car model
  if (frontTextItems.length > 0) {
    const potentialModel = frontTextItems[0].text;
    if (potentialModel.length > 3 && !patterns.toyNumber.test(potentialModel)) {
      result.carModel = potentialModel;
    }
  }

  // Process all text items
  [...frontTextItems, ...backText].forEach(item => {
    const text = item.text;

    // Look for toy number
    if (!result.toyNumber && patterns.toyNumber.test(text)) {
      result.toyNumber = text.match(patterns.toyNumber)[0];
    }

    // Look for series name
    if (!result.series && patterns.series.test(text)) {
      result.series = text.match(patterns.series)[0];
    }

    // Look for year
    if (!result.year && patterns.year.test(text)) {
      result.year = text.match(patterns.year)[0];
    }

    // Look for collection
    if (!result.collection && patterns.collection.test(text)) {
      result.collection = text.match(patterns.collection)[0];
    }

    // If we haven't found a car model yet, look for longest text that's not a known pattern
    if (!result.carModel && text.length > result.carModel.length && 
        !Object.values(patterns).some(pattern => pattern.test(text)) &&
        !text.includes('©') && !text.includes('®')) {
      result.carModel = text.trim();
    }
  });

  // Generate a title from the extracted information
  if (result.carModel) {
    result.title = result.carModel;
    if (result.series) {
      result.title += ` - ${result.series}`;
    }
    if (result.collection) {
      result.title += ` (${result.collection})`;
    }
  }

  // Generate description
  const descriptionParts = [];
  if (result.year) descriptionParts.push(`Year: ${result.year}`);
  if (result.collection) descriptionParts.push(`Collection: ${result.collection}`);
  if (result.series) descriptionParts.push(`Series: ${result.series}`);
  if (result.toyNumber) descriptionParts.push(`Toy Number: ${result.toyNumber}`);
  
  result.description = descriptionParts.join('\n');

  return result;
}
