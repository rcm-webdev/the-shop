const { GoogleSpreadsheet } = require('google-spreadsheet');
const { JWT } = require('google-auth-library');

require('dotenv').config({ path: './config/.env' });

// Column to field mapping for App-Test-4 sheet
const COLUMN_MAPPING = {
  'Box #': 'boxNumber',
  'Toy #': 'toyNumber',
  'Model Name': 'title',
  'Origin': 'year',
  'Series': 'series',
  'Wheel Variations': 'wheelVariations',
  'Front Image': 'frontImage',
  'Back Image': 'backImage'
};

class GoogleSheetService {
  constructor() {
    this.doc = null;
    this.spreadsheetId = process.env.GOOGLE_SHEET_ID;
  }

  async initialize() {
    try {
      // Create auth client
      const serviceAccountAuth = new JWT({
        email: process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL,
        key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n'),
        scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      });

      // Create a new document instance
      this.doc = new GoogleSpreadsheet(this.spreadsheetId, serviceAccountAuth);
      
      // Load the document properties
      await this.doc.loadInfo();
      return this.doc;
    } catch (error) {
      console.error('Error initializing Google Sheet:', error);
      throw error;
    }
  }

  async importSheet(sheetIndex = 4) { // Default to App-Test-4 sheet
    try {
      if (!this.doc) {
        await this.initialize();
      }

      const sheet = this.doc.sheetsByIndex[sheetIndex];
      if (!sheet) {
        throw new Error(`Sheet index ${sheetIndex} not found`);
      }

      // Load headers and rows
      await sheet.loadHeaderRow();
      const rows = await sheet.getRows();
      
      if (!rows || rows.length === 0) {
        throw new Error('No data found in the sheet');
      }

      const headers = sheet.headerValues;
      
      // Validate required columns
      const requiredColumns = ['Box #', 'Toy #', 'Model Name']; // Only these are truly required
      const missingColumns = requiredColumns.filter(col => !headers.includes(col));
      
      if (missingColumns.length > 0) {
        throw new Error(`Missing required columns: ${missingColumns.join(', ')}`);
      }
      
      return rows.map((row, index) => {
        const post = {};
        
        // Map each column to its corresponding field using the header index
        Object.entries(COLUMN_MAPPING).forEach(([columnHeader, fieldName]) => {
          const headerIndex = headers.indexOf(columnHeader);
          if (headerIndex !== -1) {
            let value = row._rawData[headerIndex];
            
            // Handle special cases
            switch (fieldName) {
              case 'year':
                value = value ? parseInt(value) : null;
                break;
              case 'wheelVariations':
                value = value ? value.split(',').map(item => item.trim()) : [];
                break;
              case 'frontImage':
              case 'backImage':
                // Handle empty image URLs
                value = value || null;
                break;
              default:
                value = value || '';
            }
            
            post[fieldName] = value;
          }
        });

        // Validate required fields
        if (!post.boxNumber || !post.toyNumber || !post.title) {
          throw new Error(`Row ${index + 1}: Missing required fields (Box #, Toy #, or Model Name)`);
        }
        
        return post;
      });
    } catch (error) {
      console.error('Error importing sheet:', error);
      throw error;
    }
  }
}

module.exports = new GoogleSheetService();

