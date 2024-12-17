# encoding:utf-8

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf
from plugins import *
import time
from loguru import logger
from config import conf, load_config, global_config
import requests
import random
from channel.chat_channel import check_contain,check_prefix

class sendType(Enum):
    ALL = "所有"  # 文本消息
    OWNER = "群主"  # 音频消息
    WHITELIST = "白名单"  # 图片消息

@plugins.register(
    name="SendMessages",
    desire_priority=-999,
    hidden=True,
    desc="A plugin that check unknown command",
    version="1.0",
    author="wujie",
)

class SendMessages(Plugin):
    kwargs={"msg":"","seconds":5,"image":""}
    mygis_sleep_minsecond= 5
    mygis_sleep_maxsecond = 10

    mygis_groups_whitelist=[]

    mygis_friends_whitelist = []

    response={}
    trigger_prefix="$sendmessages"
    instrution=None

    bIsStopReply =False

    bIsNoReply =False

    def __init__(self):
        super().__init__()
        # 根据配置获取当前的channel类型
        self.channel_type = conf().get("channel_type", "wx")
        if self.channel_type == "wx":
            try:
                # from lib import itchat
                from plugins.sendmessages.MyGISItChannel import MyGISItChannel
                self.channel = MyGISItChannel()
            except Exception as e:
                logger.error(f"未安装itchat: {e}")
        elif self.channel_type == "wxy":
            try:
                from channel.wechat.wechaty_channel import WechatyChannel
                self.channel = WechatyChannel
            except Exception as e:
                logger.error(f"未安装ntchat: {e}")
        elif self.channel_type == "wework":
            try:
                # from channel.wework.wework_channel import WeworkChannel
                # self.channel = WeworkChannel
                from plugins.sendmessages.MyGISWeworkChannel import MyGISWeworkChannel
                self.channel = MyGISWeworkChannel()

            except Exception as e:
                logger.exception(e)
                logger.error(f"未安装Wework: {e}")
        else:
            logger.error(f"不支持的channel_type: {self.channel_type}")


        try:
            self.conf = super().load_config()

            self.trigger_prefix = conf().get("plugin_trigger_prefix", "$") + "sendmessages"

            if not self.conf:
                logger.warn("[SendMessages] inited but SendMessages not found in config")
            else:
                self.updateConfig()

            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[SendMessages] inited")

        except Exception as e:
            logger.exception(e)
            raise self.handle_error(e, "[SendMessages] init failed, ignore ")
    def updateConfig(self):
        try:
            logger.info("[SendMessages] updateConfig...")

            self.mygis_sleep_minsecond = self.conf["mygis_sleep_minsecond"]
            self.mygis_sleep_maxsecond = self.conf["mygis_sleep_maxsecond"]
            self.mygis_groups_whitelist = self.conf["mygis_groups_whitelist"]
            self.mygis_friends_whitelist = self.conf["mygis_friends_whitelist"]
            self.bIsStopReply = self.conf["mygis_stop_reply"]
            self.channel.mygis_sleep_minsecond = self.mygis_sleep_minsecond
            self.channel.mygis_sleep_maxsecond = self.mygis_sleep_maxsecond
            self.channel.mygis_groups_whitelist = self.mygis_groups_whitelist
            self.channel.mygis_friends_whitelist = self.mygis_friends_whitelist
            self.channel.conf=self.conf
            self.response = self.conf["response"]
            self.instrution = self.conf["instrution"]

            logger.info("response:{}".format(self.response))
        except Exception as e:
            logger.exception(e)
    # 目前两种方式都可以。
    def on_handle_context(self, e_context: EventContext):

        content = e_context["context"].content

        # 处理 加朋友
        logger.info("type:{}".format(e_context["context"].type))
        if (e_context["context"].type == ContextType.ACCEPT_FRIEND):  # 好友申请，匹配字符串

            reply = self.channel._build_friend_request_reply(e_context["context"])
            # return
            if reply !=None:
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return reply
            else:
                return
        # 可以保留欢迎
        if (e_context["context"].type == ContextType.JOIN_GROUP):
            # e_context.action = EventAction.CONTINUE
            return

            # 处理文字
        if e_context["context"].type != ContextType.TEXT:
            return

        user = e_context["context"]["receiver"]

        bIsAdmin =False
        if user in global_config["admin_users"]:
            bIsAdmin =True

        logger.info("bIsAdmin:{}".format(bIsAdmin))
        logger.info("user:{}--admin_users{}".format(user,global_config["admin_users"]))
        logger.debug("[SendMessages] on_handle_context. content: %s" % content)
        #
        # # 如果有匹配的关键字，则不回复
        #
        logger.info("single_chat_noreply_prefix:{}".format(self.conf["single_chat_noreply_prefix"]))
        if self.check_noreply(content, self.conf["single_chat_noreply_prefix"]) is True:
            logger.warning(" sendmessages 不需要回复的关键字...{}".format(self.conf["single_chat_noreply_prefix"]))
            e_context.action = EventAction.BREAK_PASS
            return


        trigger_prefix = self.trigger_prefix
        result = self.response
        # 处理关键字回复
        for key in result.keys():
            if content in key:
                if "群" in content:
                    room = result[key]
                    self.channel.add_member_into_chatroom(roomname=room, UserName=user)
                else:
                    logger.info("{} 包含关键字:{}".format(key,content))
                    self.channel.send_rawmsg(content=result[key],to_user_name=user)
                e_context.action = EventAction.BREAK_PASS
                return
        if content.startswith(trigger_prefix):
            reply = Reply()
            reply.type = ReplyType.INFO
            newContent = content.replace(trigger_prefix,"").strip()
            args =newContent.split()
            logger.info("args:{}".format(args))
            adminList =["开始回复","停止回复","组群发","好友群发"]
            if bIsAdmin ==False:
                reply.content = "请先认证..."
                reply.type = ReplyType.INFO
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            elif len(args)==0 or  not self.check_contain(args[0],adminList):
                info = self.get_help_text()
                reply.type = ReplyType.ERROR
                reply.content = info
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return

            if args[0] == "停止回复":
                self.bIsStopReply =True
                reply.type = ReplyType.INFO
                reply.content = "停止回复 ...成功!"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return
            if args[0] == "开始回复":
                self.bIsStopReply =False
                reply.type = ReplyType.INFO
                reply.content = "开始回复 ...成功!"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return
            if  args[0]=="组群发" or args[0]=="好友群发":
                # reply.type = ReplyType.SEND_GROUPS
                # msg = args[1]

                bIsAll = False

                if args[1]=="所有":
                    bIsAll =True

                msginfo = args[2]
                if msginfo in self.instrution:
                    # 执行指令
                    sendInfos=self.instrution[msginfo]
                    for sendinfo in sendInfos:
                        msg=""
                        if args[0]=="组群发":
                            msg = self.channel.sendAllRooms(content=sendinfo, all=args[1])
                        else:
                            msg = self.channel.sendAllFriends(content=sendinfo, all=args[1])

                        self.channel.send_msg(msg_type="text", content=msg,
                                              to_user_name=user)
                else:
                    info = newContent.replace(args[0], "")
                    info = info.replace(args[1], "")
                    msg=""
                    if args[0] == "组群发":
                        msg = self.channel.sendAllRooms(content=info,all=args[1])
                    else:
                        msg = self.channel.sendAllFriends(content=info, all=args[1])

                    self.channel.send_msg(msg_type="text", content=msg,
                                  to_user_name=user)

                reply.content = "发送完毕..."
                reply.type = ReplyType.INFO
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

        if self.bIsStopReply==True:
            logger.info("系统目前 停止 回复中...")
            # 停止回复
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑


    def get_help_text(self, **kwargs):
        msg ="用法:\n"
        msg += "{} 开始回复\n".format(self.trigger_prefix)
        msg += "{} 停止回复\n".format(self.trigger_prefix)
        msg += "{} 组群发 [所有/群主/白名单] [指令/msg]\n".format(self.trigger_prefix)
        msg += "{} 好友群发 [所有/白名单] [指令/msg]\n".format(self.trigger_prefix)
        msg += "指令包括:\n"
        for key in self.instrution:
            msg += "{} \n".format(key)


        return msg

 # 判断是否含有关键字
    def check_contain(self, msg, keys_list):
        for key in keys_list:
            if key.upper() in msg.upper():
                return  True
        return False

    def check_noreply(self, msg, keys_list):
        # 如果是表情也不回复
        logger.info("msg:{},{},{}".format(msg,msg.startswith("["),msg.startswith("]")))

        if msg.startswith("[") and msg.endswith("]"):
            return True
        for key in keys_list:
            if key.upper() == msg.upper():
                return  True

        return False




