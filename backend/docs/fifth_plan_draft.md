



now lets just go one step ahead

testing phase is done development phase starts

now we do not want  to creeate UI or streamlit instread we will soly work on fastapi

and test api with fastapi doc endpoint where i can see all listed apis or maybe sometimes with postman

as we starts currently keep all those features which we already have but just in apis why

i should be able to test my api key with selected provider and model

now new chat works like if thread id is provided or not provided

now we will use dynamodb local storage 

we keep databsae seperate for each user for that we will use test-user-1

and we can change that to another user id if want currently we do not want any user auth things we can just directly past user id in payload when testing

each user has his chat history seperate

let me just make some bullet points for better undertstanding

1-first api test endpoint
2-an post generation endpoint where i provide user id idea for post and generation style and on what to generate post
3-post modification endpoint where we provide user id and thread id and modification msg
4-we save user generated posts
5-if modified we replace original with modified one
6-internally we will have some user details and saved againts his user id like its professional details
7-we save time stamp of post generation and modification
8-an endpoint where we provide user with some post generation ideas like brain storming but relevent to user profile
9-brainstorming will have some ideas as well on what to research about
10-an endpoint that returns all the data of user like his profile info and his added creators list
11-an endpoint that give thread id of all the chats/posts user has created
12-an endpoiint that give generated/modified post and conversation user has for modification saved agains that thread id
13-an endpoint where we provide an creator linkedin url and it is saved againts the user id (multiple can be saved)
14-an endpoint that give list of all added creators back with there ids
15-an endpoint through which we can run a search/playwrite thing which opens web scrape providers latest posts (they can be multiple providers or one) means multiple browser can open and multiple praywrite can run in parallel and fetch recent 5 activites
16-we saved those activites in againt that creators id 
17-an endpoint through which we can get the latest activity data return from db which are saved agains that creator id
18-an endpoint through which we get back all the recent activities data of all providers listed from db
19-remember when searching recent posts of providers in parallel and returns many data add an unique id with each post return so that when search runs again we can keep tracts what is old and what is new so that when we run search again then api only return whats new post by comparing what is already in db for that user and return only when something new found


belows are the points styles brainstroming ideas modification defualt things which we need to use for post generation modification brainstorming etc

Saved Actions
• Get topic ideas for my posts
Generate post ideas for me
Generate post ideas about any topic
Find audience pain points
Find common mistakes around my topic
Find common misconceptions people have about a topic
Brainstorm post topics
Brainstorm book recommendation about a topic
Brainstorm documentary recommendations about a topic
Brainstorm useful tools about a topic
Create posts from scratch

Create a post about a topic
Create a controversial post about a topic
Create a "top mistakes" post about a topic
Create a "daily routine" post about a topic
Create a "how to start" post about a topic
Create a motivational post about a topic
Create a "skills to become successful" post about a topic
Create a "do's and don'ts" post about a topic
Improve generated content

Change the tone of a post
Be more concise
Add content to generated content (collapsed in this image, expanded below)
Add content to generated content

Add a hook
Add a CTA
Add concrete examples

20-when some latest things found during search sraping we add them to db without replacing the old data of post so that when user want he can get all the data through that get endpoint which we have discuss
21-as each post has an id saved againts that each creator id , i want an endpoint which is used to create a variation of post which creator has posted in that we provide user id as useal (no thread id as this will be new chat) and that post id, and that creators id, we first check that creator exits post exist in db then get the post and rewrite its variant we according to the style which is already is used in creator post 
22-and we can also modify this generated post using same modifcation endpoint as above where we provide thread id returned with the generated post and usual imporatant thing in payload like user id and modification msg and return modified post
23-remember to add line space and line breaks and bullets list paragraoph if neede in post so that it do not looks like plan long text also always add some hashtags in the generated post ends relevent to post
24-an endpoint to add a new user where we provide user id and its profile details
25-an endpoint that returns all the registered user
26-by defualt add two test user test-user-1 and 2 and add some dummy prosonal details of them (let me add those details just give me those details in a file in test folder so that i can test that add user endpoint too)
27-as of now we will use llm provider model selected from .env or config file but we will have all the available options as already in config file which are used when that testing api key endpoint is called
28-update user prfile endpooint
29-delete/remove tracked creator
30-delete post or thread endpoint
31-Point 15 runs multiple parallel Playwright scrapes — that's inherently a background/long-running job. You'll likely want a job-status endpoint (started/running/done/failed) rather than expecting the scrape to finish synchronously within one request/response cycle. NOTE currently we will wait for the endpoint to end to see how its work later we will do that for now do not do backgrounad thing as currently we do not have any time out thing think error in develeopment
32-Endpoints returning lists (all posts, all creators, all activities, all users) will need limit/offset or cursor params eventually — worth designing for now even if unused in testing phase. NOTE limit the return list to say 10 for now but it will be dynamic we can adjust that limit from .env or config file
33-when llm is used in any api return the provider or model used
34-add the test things in test folder remove streamlit file but do not remove docker thing just update like we might upload our fastapi app on huggingface instead of stremalit just fastapi with docker
35-install the dynamodb local with docker i thing give path of this dir of app mean i shoudl be able to see the folder in repo named dynamodb_localdb

