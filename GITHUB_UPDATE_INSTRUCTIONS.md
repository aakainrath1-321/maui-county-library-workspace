# Update the Live Render Site

The Render deployment is already working. Do not create a new Render service.

Update the existing GitHub repository by uploading the contents of this v9 folder and committing the changes. The most important replaced files are:

- templates/base.html
- templates/home.html
- static/css/app.css
- static/js/app.js

The rest of the existing project can remain, but uploading the full folder contents is safe as long as the Gemini API key is NOT included anywhere.

After the GitHub commit, Render should auto-deploy the same service and keep the same public URL.
