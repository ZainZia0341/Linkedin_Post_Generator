LINKEDIN_POST_GENERATOR/
├── .venv/
├── app/
│   ├── llm_providers/
│   │   ├── claude.py
│   │   ├── gemini.py
│   │   ├── groq.py
│   │   └── llm.py
│   ├── nodes/
│   │   └── xyz_node.py
│   ├── conditional_edges.py
│   ├── config.py
│   ├── graph_state_schema.py
│   └── graph_state.py
├── docs/
│   └── first_plan_draft.md
├── schema\
    ├──local_db/
    └──mongodb/
├── streamlit_ui/
├── test/
│   ├── test_data/
│   ├── test_responses/
│   └── test_scripts/
├── .env
├── .gitignore
├── .python-version
├── example.env
├── main.py
├── pyproject.toml
├── dockerFile
├── README.md
├── Testing.ipynb
└── uv.lock



in my thoughts this structure will be good for streamlit UI based deployed on huggingface free CPU space with local db for now latter will replace with mongodb or dynamodb

stack

python,
Langchain,
LangGraph,
Groq/Gemini/Claude, (Free Limited APIs for llm),
Travily web search tool,
current local db
Streamlit,
Hosted on HuggingFace Space


the will worked like
a user come 
we created a local session and keep tracks of users with that session id

a button in UI telling create new chat which will create new session Id and then we will only use new information in llm calling etc

naming convention on chats will be chat1 chat2 chat3 ....

in UI we will have some setup options in left side bar section

a drop down selection for llm providers (groq gemini cluade)
then drop down selection option for the llm model to select from that specefic selected provider
then a input text field to input your API key there
and a test api key button which will check api key against that provider model

below that we will have new chat start button 
below that we will have chats list

when user click new chat if api key availble and things are selected and ok then create a new chat 

and on right side section main section of app we will have option to provider your previous linkedin post which you want to copy style

then user past and click next

then we will use AI llm which will extract key writing style pattern and save it and show to user in UI which user can edit if want

then user click next and we save/update any changes in that writing style

or user can select one of the available builtin three defualt writing styles

then in next screen we will ask user to provide the pdf of his resume if he want so that AI have the information about the person whome is he about to generate the likedin post (as if any personal data inforamtion is required in post if then AI can use those personal inforamtions)

when user click next we use AI to extract the key information of user from its resume pdf and show it to user in UI which user can change then click next and we save any changes

then we will two buttons or two cards 

1- give a topic and we will generate a post
2- research any new tranding topics

lets focus on 1 first

user click first card
a text filed come asking about the topic
user gives topic

then AI runs

web searches post generated according to writing style and if any personal information is needed then that then reviews generated post if all facts format etc are correct

when all ready 

a chat screen will open like any other chatbot where a input text field will be at buttom and post will above
user can type in input field and can changes anything if psot if required 

in answer AI will only response to any changes in post and will only return post nothing before or after it and will not entertained any new other generate question or anything else 

if user left the chat in mid or create a new chat just after providing the writing style or before providing the writing style and then come back to that chat then we will continue from where user left that chat and we will keep track of that with session id 

now what will be AI working flow

first include latest version of each module used in uv add

first use structure output for every llm call with proper json schema of output
in first llm call we get user previous post and get writing styles for that
save and show user

or user can select one of the 3 builtin defuilt writing styles showed in UI and click next in that case we direcly goes to resume step  

in second llm call we get user resume in pdf (optional user might not have any resume at all)
and AI show user its details if he wants to edit some things and save (this showing thing in UI might be json as we are using strucutre output)

after that user selects a card (option 1)

and provide a topic

then our main graph starts from there

first node will be 

conversation memory checker 

use langraph 

from langchain.messages import RemoveMessage  

def delete_messages(state):
    messages = state["messages"]
    if len(messages) > 2:
        # remove the earliest two messages
        return {"messages": [RemoveMessage(id=m.id) for m in messages[:2]]}


to keep only last 10 messages in chat

second node
llm guadrail protection as at this point we already have the generated post and we will save it in state
and any off topic general QA will be reply back like sorry I can not help you with that i can only modify this generated Linkedin post

then show the post

so before second node i think there will be a conditional edge which will checks withet it is guadrail topic or post modification topic

if guidrail then it past the call to another node which will reply back to user with a hard coded msg we do not need to use llm for that

if post editing modification topic then pass to another node which will use LLM to modify the post accodting to user msgs current msg and it will have conversation history as well

then another llm calls will check the generated post and verify is it ok according to user current modificationr request msg and writing style and users resume data if any required and provided if all checks passed then generaed psot is shown to user if there is some mistke in generated modifies post then it will send back to post modification node with the help of langgraph goto command
 
Command(
  self,
  *,
  graph: str | None = None,
  update: Any | None = None,
  resume: dict[str, Any] | Any | None = None,
  goto: Send | Sequence[Send | N] | N = ()
)

then it will regenrate post means do modification again accoding to feedback msg user msg writing style and resume data

then again it will be check if pass then ok if fail then generate again

max 3 tries
then return what ever post we get 

in final return msg include the provider and llm model used


in second card option 2

implement a langchain deep search (seperate from graph in seperate file)

where we do deep research according to user's resume data if provided and return as manau as possible tranding things accoding to user data

if resume is not provided then user is aksed to provide the details on which deep search has to be done

if card 2 is selected and data is provided deep search results are display on screen like chat UI as previous but this time text input field will be disable and only results are shown 

make docker file
streamlit code in streamlit folder

alter directory structure if required and meet industry standards 

also after analyzing this details doc mak a new markdown file named


second_plan_draft.py

in which write down all the details on this plan flow and how you will do it

also mention anything you cam accross during the implementation phase

write down all the details about what have you done what was requried and any limitation if any in this markdown file


also add test data in test folder

test scripts

and test return response data so that i can check the test 

perform all edge cases test after implementation

and use local storage for now used folder schema in which you can find folder local_db

in example.env

inlcude all relevent envs variables

see the example.env for env and api keys data and take those api keys which you need

and arrange the data of example.env section wise with commit without changing anythign else in find wether we need that thing in this app or not just re order them better


now do you work give markdown file and code and good directory structure

do not use logs

use prints i want to see prints in console 

also in Testing.ipynb file add a line through which i can visual lize the graph created with the image graph module of langgraph you can find it online