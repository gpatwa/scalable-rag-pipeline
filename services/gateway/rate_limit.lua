-- services/gateway/rate_limit.lua
-- Token Bucket Algorithm implementation for OpenResty/Nginx

local redis = require "resty.redis"
local red = redis:new()

-- 1. Connect to Redis (High Speed)
red:set_timeout(100) -- 100ms timeout
local ok, err = red:connect("rag-redis-prod", 6379)
if not ok then
    ngx.log(ngx.ERR, "failed to connect to redis: ", err)
    return ngx.exit(500)
end

-- 2. Identify Client (IP or API Key)
local client_ip = ngx.var.remote_addr
local key = "rate_limit:" .. client_ip

-- 3. Rate Limit Logic (e.g., 100 req / minute)
local limit = 100
local current = red:incr(key)

if current == 1 then
    red:expire(key, 60) -- Reset count every 60 seconds
end

if current > limit then
    ngx.status = 429
    ngx.say("Rate limit exceeded. Try again later.")
    return ngx.exit(429)
end

-- 4. Pass traffic
-- If we reach here, the request is allowed