import threading

## This module handles the event-passing system between the UI and the 
# devices. Objects may publish events, subscribe to them, and unsubscribe from
# them.

## Maps event types to lists of (priority, function) tuples to call when
# those events occur.
eventToSubscriberMap = {}

## As eventToSubscriberMap, except that these subscribers only care about the
# next event (i.e. they unsubscribe as soon as the event happens once).
eventToOneShotSubscribers = {}

## Lock around the above two dicts.
subscriberLock = threading.Lock()

## Pass the given event to all subscribers.
def publish(eventType, *args, **kwargs):
    for priority, subscribeFunc in eventToSubscriberMap.get(eventType, []):
        subscribeFunc(*args, **kwargs)
    with subscriberLock:
        if eventType in eventToOneShotSubscribers:
            for subscribeFunc in eventToOneShotSubscribers[eventType]:
                subscribeFunc(*args, **kwargs)
            del eventToOneShotSubscribers[eventType]


## Add a new function to the list of those to call when the event occurs.
# \param priority Determines what order functions are called in when the event
#        occurs. Lower numbers go sooner.
def subscribe(eventType, func, priority = 100):
    with subscriberLock:
        if eventType not in eventToSubscriberMap:
            eventToSubscriberMap[eventType] = []
        eventToSubscriberMap[eventType].append((priority, func))
        eventToSubscriberMap[eventType].sort()


## Add a new function to do a one-shot subscription.
def oneShotSubscribe(eventType, func):
    with subscriberLock:
        if eventType not in eventToOneShotSubscribers:
            eventToOneShotSubscribers[eventType] = []
        eventToOneShotSubscribers[eventType].append(func)


## Remove a function from the list of subscribers.
def unsubscribe(eventType, func):
    with subscriberLock:
        curSubscribers = eventToSubscriberMap.get(eventType, [])
        for i, (priority, subscriberFunc) in enumerate(curSubscribers):
            if func == subscriberFunc:
                del curSubscribers[i]
                return


## Call the specified function with the provided arguments, and then wait for
# the named event to occur.
def executeAndWaitFor(eventType, func, *args, **kwargs):
    newLock = threading.Lock()
    newLock.acquire()
    result = []
    def releaser(*args):
        result.extend(args)
        newLock.release()
    oneShotSubscribe(eventType, releaser)
    func(*args, **kwargs)
    # Note that since newLock is already locked, this will block until it is
    # released.
    with newLock:
        if len(result) == 1:
            return result[0]
        return result




