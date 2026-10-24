const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);
// The API client, types and mock data live in ../shared and are used by web and mobile.
config.watchFolders = [path.resolve(__dirname, "../shared")];
module.exports = config;
