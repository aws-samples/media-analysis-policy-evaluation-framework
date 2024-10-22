import { fetchAuthSession } from 'aws-amplify/auth';
import { post, get, put } from 'aws-amplify/api';

async function FetchPost(path, reqbody=null, apiName='ExtractionService') {
  var request = await ContructRequest(path, reqbody, apiName);
  const restOperation =  await post(request);
  const { body, statusCode } = await restOperation.response;
  return await body.json();
}

async function FetchPut(path, reqbody=null, apiName='ExtractionService') {
  var request = await ContructRequest(path, reqbody, apiName);
  const restOperation =  await put(request);
  const { body, statusCode } = await restOperation.response;
  return await body.json();
}

async function FetchGet(path, reqbody=null, apiName='ExtractionService') {
  var request = await ContructRequest(path, reqbody, apiName);
  const restOperation =  await get(request);
  const { body, statusCode } = await restOperation.response;
  return await body.json();
}

async function ContructRequest(path, reqbody, apiName) {
  return {
    apiName: apiName,
    path: path,
    options: {
      body: reqbody,
      headers: {
        Authorization: (await fetchAuthSession()).tokens?.idToken?.toString(),
        "x-api-key": process.env.REACT_APP_APIGATEWAY_API_KEY
      },
      queryParams: null
    }
  }
}

export {FetchPost, FetchPut, FetchGet};