# Dynamicbeat

This is our modified dynamicbeat program that will give the proper feedback gotten from the API to be published onto the Kanban board.


`~` refers to the main Scorestack folder if downloaded from the GitHub repo.

**Original Location** : ~/dynamicbeat/pkg/checktypes/http/http.go

## Further Extension
If you need to modify the return message even more for some reason, you'll need to recompile the code according to the instructions within Scorestack. But I'll be nice and give some steps.


```
    export GOPATH=${GOPATH}/src/github.com/scorestack/scorestack/dynamicbeat
```

This is really the only prerequisite step that you need so the steps in the Makefile will know where to get the basic source from (I think - it's all sorcery really).

After that, you just do a simple

```
    make dynamicbeat
```

and this will give you the modified dynamicbeat that will update the main Scorestack UI.

Then you just run it as normal with `./dynamicbeat <task>` and make sure you have the *dynamicbeat.yml* file in the directory that you run it from.

