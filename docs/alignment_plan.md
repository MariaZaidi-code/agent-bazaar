# Documents Page Alignment Plan

## Problem
The documents page uses inconsistent styling compared to the rest of the application:
- Uses `panel` class instead of `window-card` 
- Upload section has a different visual style than other pages
- Layout doesn't align with marketplace/dashboard patterns
- Missing consistent `window-bar` headers

## Solution
Update the documents page HTML and CSS to align with the rest of the project's design system:
1. Convert `panel` to `window-card` structure
2. Add proper `window-bar` headers
3. Align upload form styling with marketplace search/filter controls
4. Ensure document detail and ask sections match other card styles
5. Update CSS in premium.css to support the new structure

## Files to Modify
- `app/web/templates/index.html` - Update documents page HTML structure
- `app/web/static/premium.css` - Update/align document section styles
