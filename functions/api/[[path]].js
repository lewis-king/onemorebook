import { handleRequest } from '../../cloudflare/api.mjs';

export const onRequest = ({ request, env }) => handleRequest(request, env);
