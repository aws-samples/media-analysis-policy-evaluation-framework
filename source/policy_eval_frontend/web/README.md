# AWS GenAI media analysis and policy evaluation

The static website is built using [React](https://github.com/facebook/create-react-app). It needs to be deployed together with the rest of the CDK package for a fully functioning solution. 

## To run the REACT app on your local machine

You can connect this REACT app to the backend services deployed using the CDK Backend stack by configuring the appropriate parameters in the .env file.

Replace the variables in the `.env.template` file with the services deployed using the CDK package at the parent level of this folder. (You can find the variable values from the main CloudFormation stack output.) Rename the file to `.env`.

In the project directory `web`, you can run:
### `npm install`

If error:
### `npm install --force`

Run instance on local machine
### `npm start`

## To prepare a build that can be deployed together with the other backend code

### `npm run build`
This command will generate a new build under the `build` folder with placeholders for the backend service URLs.

Next, you can follow the README at the root level of this repository to deploy the solution, which includes both the backend AWS services and this React application.