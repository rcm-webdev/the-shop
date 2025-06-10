const mongoose = require("mongoose");

const PostSchema = new mongoose.Schema({
  title: {
    type: String,
    required: false,
  },
  frontImage: {
    type: String,
    required: true,
  },
  backImage: {
    type: String,
    required: true,
  },
  frontImageCloudinaryId: {
    type: String,
    required: true,
  },
  backImageCloudinaryId: {
    type: String,
    required: true,
  },
  caption: {
    type: String,
    required: false,
  },
  tags: {
    type: [String],
    default: [],
  },
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: "User",
  },
  createdAt: {
    type: Date,
    default: Date.now,
  },
});

module.exports = mongoose.model("Post", PostSchema);
